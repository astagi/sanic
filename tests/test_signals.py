import asyncio
from inspect import isawaitable
from typing import Type

import pytest

from sanic import Blueprint
from sanic.exceptions import InvalidSignal, SanicException


def test_add_signal(app):
    @app.signal("foo.bar.baz")
    def sync_signal(*_):
        ...

    @app.signal("foo.bar.baz")
    async def async_signal(*_):
        ...

    assert len(app.signal_router.routes) == 1


@pytest.mark.parametrize(
    "signal",
    (
        "<foo>.bar.bax",
        "foo.<bar>.baz",
        "foo",
        "foo.bar",
        "foo.bar.baz.qux",
    ),
)
def test_invalid_signal(app, signal):
    with pytest.raises(InvalidSignal, match=f"Invalid signal event: {signal}"):

        @app.signal(signal)
        def handler():
            ...


@pytest.mark.asyncio
async def test_dispatch_signal_triggers_multiple_handlers(app):
    counter = 0

    @app.signal("foo.bar.baz")
    def sync_signal(*_):
        nonlocal counter

        counter += 1

    @app.signal("foo.bar.baz")
    async def async_signal(*_):
        nonlocal counter

        counter += 1

    app.signal_router.finalize()

    await app.dispatch("foo.bar.baz")
    assert counter == 2

    await app.dispatch("foo", "bar", "baz")
    assert counter == 4


@pytest.mark.asyncio
async def test_dispatch_signal_triggers_triggers_event(app):
    counter = 0

    @app.signal("foo.bar.baz")
    def sync_signal(*args):
        nonlocal app
        nonlocal counter
        signal, *_ = app.signal_router.get("foo.bar.baz")
        counter += signal.ctx.event.is_set()

    app.signal_router.finalize()

    await app.dispatch("foo.bar.baz")
    signal, *_ = app.signal_router.get("foo.bar.baz")

    assert counter == 1


@pytest.mark.asyncio
async def test_dispatch_signal_triggers_dynamic_route(app):
    counter = 0

    @app.signal("foo.bar.<baz:int>")
    def sync_signal(baz):
        nonlocal counter

        counter += baz

    app.signal_router.finalize()

    await app.dispatch("foo.bar.9")
    assert counter == 9


@pytest.mark.asyncio
async def test_dispatch_signal_triggers_with_requirements(app):
    counter = 0

    @app.signal("foo.bar.baz", requirements={"one": "two"})
    def sync_signal(*_):
        nonlocal counter
        counter += 1

    app.signal_router.finalize()

    await app.dispatch("foo.bar.baz")
    assert counter == 0
    await app.dispatch("foo.bar.baz", where={"one": "two"})
    assert counter == 1


@pytest.mark.asyncio
async def test_dispatch_signal_triggers_with_context(app):
    counter = 0

    @app.signal("foo.bar.baz")
    def sync_signal(amount):
        nonlocal counter
        counter += amount

    app.signal_router.finalize()

    await app.dispatch("foo.bar.baz", context={"amount": 9})
    assert counter == 9


@pytest.mark.asyncio
async def test_dispatch_signal_triggers_with_context_fail(app):
    counter = 0

    @app.signal("foo.bar.baz")
    def sync_signal(amount):
        nonlocal counter
        counter += amount

    app.signal_router.finalize()

    task = await app.dispatch("foo.bar.baz", {"amount": 9})
    with pytest.raises(
        SanicException,
        match=(
            "Cannot dispatch with supplied event: foo.bar.baz. If you wanted "
            "to pass context or where, define them as keyword arguments."
        ),
    ):
        await task


@pytest.mark.asyncio
async def test_dispatch_signal_triggers_on_bp(app):
    bp = Blueprint("bp")

    app_counter = 0
    bp_counter = 0

    @app.signal("foo.bar.baz")
    def app_signal():
        nonlocal app_counter
        app_counter += 1

    @bp.signal("foo.bar.baz")
    def bp_signal():
        nonlocal bp_counter
        bp_counter += 1

    app.blueprint(bp)
    app.signal_router.finalize()

    await app.dispatch("foo.bar.baz")
    assert app_counter == 1
    assert bp_counter == 1

    await bp.dispatch("foo.bar.baz")
    assert app_counter == 1
    assert bp_counter == 2


@pytest.mark.asyncio
async def test_dispatch_signal_triggers_event(app):
    app_counter = 0

    @app.signal("foo.bar.baz")
    def app_signal():
        ...

    async def do_wait():
        nonlocal app_counter
        await app.event("foo.bar.baz")
        app_counter += 1

    app.signal_router.finalize()

    await app.dispatch("foo.bar.baz")
    waiter = app.event("foo.bar.baz")
    assert isawaitable(waiter)

    fut = asyncio.ensure_future(do_wait())
    await app.dispatch("foo.bar.baz")
    await fut

    assert app_counter == 1


def test_bad_finalize(app):
    counter = 0

    @app.signal("foo.bar.baz")
    def sync_signal(amount):
        nonlocal counter
        counter += amount

    with pytest.raises(
        RuntimeError, match="Cannot finalize signals outside of event loop"
    ):
        app.signal_router.finalize()