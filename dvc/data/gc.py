def gc(odb, used, jobs=None, cache_odb=None, shallow=True):
    import itertools

    from dvc.data.tree import Tree
    from dvc.objects.errors import ObjectDBPermissionError
    from dvc.utils.threadpool import ThreadPoolExecutor

    if odb.read_only:
        raise ObjectDBPermissionError("Cannot gc read-only ODB")
    if not cache_odb:
        cache_odb = odb
    used_hashes = set()
    for hash_info in used:
        used_hashes.add(hash_info.value)
        if hash_info.isdir and not shallow:
            tree = Tree.load(cache_odb, hash_info)
            used_hashes.update(
                entry_obj.hash_info.value for _, entry_obj in tree
            )

    def _is_dir_hash(_hash):
        from dvc.hash_info import HASH_DIR_SUFFIX

        return _hash.endswith(HASH_DIR_SUFFIX)

    # group hashes to that we can remove dirs first
    to_remove = dict(
        itertools.groupby(
            filter(
                lambda hash_: hash_ not in used_hashes,
                odb.all(jobs, odb.fs_path),
            ),
            key=_is_dir_hash,
        )
    )
    dir_hashes = list(to_remove.get(True, []))
    file_hashes = list(to_remove.get(False, []))

    if not (dir_hashes or file_hashes):
        return False

    from dvc.data.transfer import _log_exceptions
    from dvc.progress import Tqdm

    with Tqdm(
        total=len(dir_hashes), unit="dirs", desc="Cleaning dirs"
    ) as pbar:
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            wrapper = pbar.wrap_fn(
                _log_exceptions(
                    # backward compatibility
                    odb._remove_unpacked_dir  # pylint: disable=protected-access
                )
            )
            executor.imap_unordered(wrapper, dir_hashes)

    with Tqdm(
        total=len(file_hashes), unit="objs", desc="Cleaning objects"
    ) as pbar:
        with ThreadPoolExecutor(max_workers=jobs) as executor:

            def remover(hash_):
                fs_path = odb.path_to_hash(hash_)
                odb.fs.remove(fs_path)

            wrapper = pbar.wrap_fn(_log_exceptions(remover))
            executor.imap_unordered(wrapper, file_hashes)

    return True
