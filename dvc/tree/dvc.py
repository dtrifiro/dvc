import logging
import os
import typing

from dvc.exceptions import OutputNotFoundError
from dvc.path_info import PathInfo
from dvc.utils import relpath

from ._metadata import Metadata
from .base import BaseTree

if typing.TYPE_CHECKING:
    from dvc.output.base import BaseOutput


logger = logging.getLogger(__name__)


class DvcTree(BaseTree):  # pylint:disable=abstract-method
    """DVC repo tree.

    Args:
        repo: DVC repo.
    """

    scheme = "local"
    PARAM_CHECKSUM = "md5"

    def __init__(self, repo):
        super().__init__(repo, {"url": repo.root_dir})

    def _find_outs(self, path, *args, **kwargs):
        outs = self.repo.find_outs_by_path(path, *args, **kwargs)

        def _is_cached(out):
            return out.use_cache

        outs = list(filter(_is_cached, outs))
        if not outs:
            raise OutputNotFoundError(path, self.repo)

        return outs

    def _get_granular_hash(
        self, path_info: PathInfo, out: "BaseOutput", remote=None
    ):
        assert isinstance(path_info, PathInfo)
        # NOTE: use string paths here for performance reasons
        key = tuple(relpath(path_info, out.path_info).split(os.sep))
        out.get_dir_cache(remote=remote)
        file_hash = out.hash_info.dir_info.trie.get(key)
        if file_hash:
            return file_hash
        raise FileNotFoundError

    def open(  # type: ignore
        self, path: PathInfo, mode="r", encoding="utf-8", remote=None, **kwargs
    ):  # pylint: disable=arguments-differ
        try:
            outs = self._find_outs(path, strict=False)
        except OutputNotFoundError as exc:
            raise FileNotFoundError from exc

        if len(outs) != 1 or (
            outs[0].is_dir_checksum and path == outs[0].path_info
        ):
            raise IsADirectoryError

        out = outs[0]
        if out.changed_cache(filter_info=path):
            from dvc.config import NoRemoteError

            try:
                remote_obj = self.repo.cloud.get_remote(remote)
            except NoRemoteError:
                raise FileNotFoundError
            if out.is_dir_checksum:
                checksum = self._get_granular_hash(path, out).value
            else:
                checksum = out.hash_info.value
            remote_info = remote_obj.cache.hash_to_path_info(checksum)
            return remote_obj.tree.open(
                remote_info, mode=mode, encoding=encoding
            )

        if out.is_dir_checksum:
            checksum = self._get_granular_hash(path, out).value
            cache_path = out.cache.hash_to_path_info(checksum).url
        else:
            cache_path = out.cache_path
        return open(cache_path, mode=mode, encoding=encoding)

    def exists(self, path):  # pylint: disable=arguments-differ
        try:
            self.metadata(path)
            return True
        except FileNotFoundError:
            return False

    def isdir(self, path):  # pylint: disable=arguments-differ
        try:
            meta = self.metadata(path)
            return meta.isdir
        except FileNotFoundError:
            return False

    def check_isdir(self, path_info, outs):
        if len(outs) != 1:
            return True

        out = outs[0]
        if not out.is_dir_checksum:
            return out.path_info != path_info
        if out.path_info == path_info:
            return True

        try:
            self._get_granular_hash(path_info, out)
            return False
        except FileNotFoundError:
            return True

    def isfile(self, path):  # pylint: disable=arguments-differ
        try:
            meta = self.metadata(path)
            return meta.isfile
        except FileNotFoundError:
            return False

    def _fetch_dir(self, out, **kwargs):
        # pull dir cache if needed
        out.get_dir_cache(**kwargs)

        dir_cache = out.dir_cache
        if not dir_cache:
            raise FileNotFoundError

        from dvc.objects import Tree

        hash_info = Tree.save_dir_info(out.cache, dir_cache)
        if hash_info != out.hash_info:
            raise FileNotFoundError

    def _add_dir(self, trie, out, **kwargs):
        self._fetch_dir(out, **kwargs)

        base = out.path_info.parts
        for key in out.dir_cache.trie.iterkeys():  # noqa: B301
            trie[base + key] = None

    def _walk(self, root, trie, topdown=True, **kwargs):
        dirs = set()
        files = []

        out = trie.get(root.parts)
        if out and out.is_dir_checksum:
            self._add_dir(trie, out, **kwargs)

        root_len = len(root.parts)
        for key, out in trie.iteritems(prefix=root.parts):  # noqa: B301
            if key == root.parts:
                continue

            name = key[root_len]
            if len(key) > root_len + 1 or (out and out.is_dir_checksum):
                dirs.add(name)
                continue

            files.append(name)

        assert topdown
        dirs = list(dirs)
        yield root.fspath, dirs, files

        for dname in dirs:
            yield from self._walk(root / dname, trie)

    def walk(self, top, topdown=True, onerror=None, **kwargs):
        from pygtrie import Trie

        assert topdown
        root = PathInfo(os.path.abspath(top))
        try:
            meta = self.metadata(root)
        except FileNotFoundError:
            if onerror is not None:
                onerror(FileNotFoundError(top))
            return

        if not meta.isdir:
            if onerror is not None:
                onerror(NotADirectoryError(top))
            return

        trie = Trie()
        for out in meta.outs:
            trie[out.path_info.parts] = out

            if out.is_dir_checksum and root.isin_or_eq(out.path_info):
                self._add_dir(trie, out, **kwargs)

        yield from self._walk(root, trie, topdown=topdown, **kwargs)

    def walk_files(self, path_info, **kwargs):
        for root, _, files in self.walk(path_info):
            for fname in files:
                # NOTE: os.path.join is ~5.5 times slower
                yield PathInfo(f"{root}{os.sep}{fname}")

    def isdvc(self, path, recursive=False, strict=True):
        try:
            meta = self.metadata(path)
        except FileNotFoundError:
            return False

        recurse = recursive or not strict
        return meta.output_exists if recurse else meta.is_output

    def isexec(self, path_info):  # pylint: disable=unused-argument
        return False

    def get_dir_hash(self, path_info, name, **kwargs):
        try:
            outs = self._find_outs(path_info, strict=True)
            if len(outs) == 1 and outs[0].is_dir_checksum:
                out = outs[0]
                # other code expects us to fetch the dir at this point
                self._fetch_dir(out, **kwargs)
                assert out.hash_info.name == name
                return out.hash_info
        except OutputNotFoundError:
            pass

        return super().get_dir_hash(path_info, name, **kwargs)

    def get_file_hash(self, path_info, name):
        assert name == "md5"
        outs = self._find_outs(path_info, strict=False)
        if len(outs) != 1:
            raise OutputNotFoundError
        out = outs[0]
        if out.is_dir_checksum:
            return self._get_granular_hash(path_info, out)
        return out.hash_info

    def metadata(self, path_info):
        path_info = PathInfo(os.path.abspath(path_info))

        try:
            outs = self._find_outs(path_info, strict=False, recursive=True)
        except OutputNotFoundError as exc:
            raise FileNotFoundError from exc

        meta = Metadata(path_info=path_info, outs=outs, repo=self.repo)
        meta.isdir = meta.isdir or self.check_isdir(meta.path_info, meta.outs)
        return meta
