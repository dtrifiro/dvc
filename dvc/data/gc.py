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

    to_remove = filter(
        lambda hash_: hash_ not in used_hashes,
        odb.all(jobs, odb.fs_path),
    )

    from dvc.data.transfer import _log_exceptions
    from dvc.progress import Tqdm

    deleted = False
    for is_dir_hash, hashes in itertools.groupby(
        to_remove, _is_dir_hash
    ):  # by looping on the groupby, we run over dir hashes first, which should be removed first
        hashes = list(hashes)
        if hashes:
            deleted = True
        else:
            continue

        if is_dir_hash:
            unit = "dirs"
            desc = "Cleaning dirs"

            def remover(hash_):
                # backward compatibility
                odb._remove_unpacked_dir(  # pylint: disable=protected-access
                    hash_
                )

        else:
            unit = "objs"
            desc = "Cleaning objects"

            def remover(hash_):
                fs_path = odb.path_to_hash(hash_)
                odb.fs.remove(fs_path)

        with Tqdm(total=len(hashes), unit=unit, desc=desc) as pbar:
            with ThreadPoolExecutor(max_workers=jobs) as executor:
                executor.imap_unordered(
                    pbar.wrap_fn(_log_exceptions(remover), hashes)
                )

    return deleted
