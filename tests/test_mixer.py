from __future__ import annotations

from typing import Callable, cast

import colour
import pytest

from pyflp.mixer import Insert, InsertDock, Mixer, MixerID, MixerParamsEvent

from .conftest import ModelFixture

InsertFixture = Callable[[str], Insert]


@pytest.fixture
def get_insert(get_model: ModelFixture):
    def wrapper(preset: str):
        # Parse as Mixer to get events, because an Insert cannot parse
        # MixerID.Params which holds most of its information.
        mixer = get_model(f"inserts/{preset}", Mixer)

        # A preset stores items only for a single insert, currently thats 32 per
        # insert. Pass these to Insert's constructor. This mimics Mixer's normal
        # behaviour, however that depends on InsertID.Output as a marker to indicate
        # the end of an Insert, which surprisingly isn't a part of presets.
        params = cast(MixerParamsEvent, mixer.events_asdict().pop(MixerID.Params)[0])
        items = tuple(params.items.values())[0]
        return Insert(*mixer.events_astuple(), index=0, max_slots=10, params=items)

    return wrapper


def test_insert_bypassed(get_insert: InsertFixture):
    assert get_insert("effects-bypassed.fst").bypassed


def test_insert_channels_swapped(get_insert: InsertFixture):
    assert get_insert("channels-swapped.fst").channels_swapped


def test_insert_color(get_insert: InsertFixture):
    assert get_insert("colored.fst").color == colour.Color("#FF1414")


def test_insert_dock(inserts: tuple[Insert, ...]):
    for insert in inserts:
        if insert.name in ("Docked left", "Master"):
            assert insert.dock == InsertDock.Left
        # fmt: off
        elif (
            insert.name == "Docked right" or
            insert.__index__() in (101, 102, 103, 104)
        ):
            # fmt: on
            assert insert.dock == InsertDock.Right
        else:
            assert insert.dock == InsertDock.Middle


def test_insert_enabled(get_insert: InsertFixture):
    assert not get_insert("disabled.fst").enabled


def test_insert_locked(get_insert: InsertFixture):
    assert get_insert("locked.fst").locked


def test_insert_pan(get_insert: InsertFixture):
    assert get_insert(r"100%-left.fst").pan == -6400
    assert get_insert(r"100%-right.fst").pan == 6400


def test_insert_polarity_reversed(get_insert: InsertFixture):
    assert get_insert("polarity-reversed.fst").polarity_reversed


def test_insert_routes(inserts: tuple[Insert, ...]):
    assert not tuple(inserts[5].routes)


def test_insert_stereo_separation(get_insert: InsertFixture):
    assert get_insert(r"100%-merged.fst").stereo_separation == 64
    assert get_insert(r"100%-separated.fst").stereo_separation == -64


# def test_insert_eq(get_insert: InsertFixture):
#     for insert in inserts:
#         if insert.name == "Post EQ":
#             assert insert.eq.low.freq == 0
#             assert insert.eq.low.gain == 1800
#             assert insert.eq.low.reso == 0
#             assert insert.eq.mid.freq == 33145
#             assert insert.eq.mid.gain == 0
#             assert insert.eq.mid.reso == 17500
#             assert insert.eq.high.freq == 55825
#             assert insert.eq.high.gain == -1800
#             assert insert.eq.high.reso == 65536


def test_mixer(mixer: Mixer):
    assert mixer.apdc
    assert len(mixer) == mixer.max_inserts == 127
    assert mixer.max_slots == 10
