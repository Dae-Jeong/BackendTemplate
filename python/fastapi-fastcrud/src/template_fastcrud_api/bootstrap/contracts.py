from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack

from fastapi import FastAPI

type PrepareResources = Callable[[FastAPI, AsyncExitStack], Awaitable[None]]
type Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]
