from concurrent import futures
from itertools import islice
from typing import Any, Callable, Iterable, Iterator, Set, TypeVar

_T = TypeVar("_T")


class ThreadPoolExecutor(futures.ThreadPoolExecutor):
    _max_workers: int

    @property
    def max_workers(self) -> int:
        return self._max_workers

    def imap_unordered(
        self, fn: Callable[..., _T], *iterables: Iterable[Any]
    ) -> Iterator[_T]:
        """Lazier version of map that does not preserve ordering of results.

        It does not create all the futures at once to reduce memory usage.
        """

        def create_taskset(n: int) -> Set[futures.Future]:
            return {self.submit(fn, *args) for args in islice(it, n)}

        it = zip(*iterables)
        tasks = create_taskset(self.max_workers * 5)
        timeouts = 0
        while tasks:
            done, tasks = futures.wait(
                tasks, return_when=futures.FIRST_COMPLETED, timeout=20
            )
            for fut in done:
                yield fut.result()
            if not done:
                timeouts += 1
                print(f"timeout {timeouts}")
            tasks.update(create_taskset(len(done)))
