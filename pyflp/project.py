# PyFLP - An FL Studio project file (.flp) parser
# Copyright (C) 2022 demberto
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. This program is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details. You should have received a copy of the
# GNU General Public License along with this program. If not, see
# <https://www.gnu.org/licenses/>.

import datetime
import enum
import math
import pathlib
import sys
from typing import List, Optional, Tuple, Type, Union, cast

if sys.version_info >= (3, 8):
    from typing import Final, TypedDict, final
else:
    from typing_extensions import Final, TypedDict, final

if sys.version_info >= (3, 11):
    from typing import Unpack
else:
    from typing_extensions import Unpack

from ._base import (
    DATA,
    DWORD,
    TEXT,
    WORD,
    AnyEvent,
    AsciiEvent,
    BoolEvent,
    EventEnum,
    EventProp,
    FLVersion,
    I16Event,
    I32Event,
    KWProp,
    MultiEventModel,
    StructBase,
    StructEventBase,
    U8Event,
    U32Event,
)
from .arrangement import (
    ArrangementID,
    Arrangements,
    ArrangementsID,
    TimeMarkerID,
    TrackID,
)
from .channel import ChannelID, Rack, RackID
from .exceptions import ExpectedValue, InvalidValue, PropertyCannotBeSet, UnexpectedType
from .mixer import InsertID, Mixer, MixerID, SlotID
from .pattern import PatternID, Patterns, PatternsID
from .plugin import PluginID

DELPHI_EPOCH: Final = datetime.datetime(1899, 12, 30)
VALID_PPQS: Final = (24, 48, 72, 96, 120, 144, 168, 192, 384, 768, 960)


@final
class TimestampStruct(StructBase):
    PROPS = {"created_on": "d", "time_spent": "d"}


@final
class TimestampEvent(StructEventBase):
    STRUCT = TimestampStruct


@enum.unique
class PanLaw(enum.IntEnum):
    Circular = 0
    Triangular = 2


@enum.unique
class FileFormat(enum.IntEnum):
    """File formats used by FL Studio.

    FST (FL Studio State) files: New in FL Studio version 2.5.0.
    """

    None_ = -1
    """Temporary"""

    Project = 0
    """FL Studio project (*.flp)."""

    Score = 0x10
    """FL Studio score (*.fsc). Stores pattern notes and controller events."""

    Automation = 24
    """Stores controller events and automation channels as FST."""

    ChannelState = 0x20
    """Entire channel (including plugin events). Stored as FST."""

    PluginState = 0x30
    """Events of a native plugin on a channel or insert slot. Stored as FST."""

    GeneratorState = 0x31
    """Plugins events of a VST instrument. Stored as FST."""

    FXState = 0x32
    """Plugin events of a VST effect. Stored as FST."""

    InsertState = 0x40
    """Insert and all its slots. Stored as FST."""

    _ProbablyPatcher = 0x50  # TODO Patcher presets are stored as `PluginState`.


class ProjectID(EventEnum):
    LoopActive = (9, BoolEvent)  # TODO Is this for patterns or arrangements?
    ShowInfo = (10, BoolEvent)
    _Volume = (12, U8Event)
    PanLaw = (23, U8Event)
    Licensed = (28, BoolEvent)
    _TempoCoarse = WORD + 2
    Pitch = (WORD + 16, I16Event)
    _TempoFine = WORD + 29
    CurGroupId = (DWORD + 18, I32Event)
    Tempo = (DWORD + 28, U32Event)
    FLBuild = (DWORD + 31, U32Event)
    Title = TEXT + 2
    Comments = TEXT + 3
    Url = TEXT + 5
    _RTFComments = TEXT + 6
    FLVersion = (TEXT + 7, AsciiEvent)
    Licensee = TEXT + 8
    DataPath = TEXT + 10
    Genre = TEXT + 14
    Artists = TEXT + 15
    Timestamp = (DATA + 29, TimestampEvent)


class _ProjectKW(TypedDict):
    channel_count: int
    ppq: int
    format: FileFormat


@final
class Project(MultiEventModel):
    def __init__(self, *events: AnyEvent, **kw: Unpack[_ProjectKW]):
        super().__init__(*events, **kw)

    def __repr__(self) -> str:
        return f"FL Studio {str(self.version)} {self.format.name}"

    def _collect_events(self, *enums: Type[EventEnum]) -> List[AnyEvent]:
        events: List[AnyEvent] = []
        for event in self._events_tuple:
            for enum in enums:
                if event.id in enum:
                    events.append(event)
                    break
        return events

    @property
    def arrangements(self) -> Arrangements:
        return Arrangements(
            *self._collect_events(ArrangementID, ArrangementsID, TrackID, TimeMarkerID),
            version=self.version,
        )

    artists = EventProp[str](ProjectID.Artists)

    @property
    def channel_count(self) -> int:
        """Number of channels in the rack.

        For Patcher presets, the total number of plugins used inside it.

        Raises:
            InvalidValue: When a value less than zero is tried to be set.
        """
        return self._kw["channel_count"]

    @channel_count.setter
    def channel_count(self, value: int):
        if value < 0:
            raise InvalidValue("Channel count cannot be less than zero")
        self._kw["channel_count"] = value

    @property
    def channels(self) -> Rack:
        """Iterator over channels and some channel rack properties."""
        events: List[AnyEvent] = []
        for event in self._events_tuple:
            if event.id == InsertID.Flags:
                break

            for enum in (ChannelID, DisplayGroupID, PluginID, RackID):
                if event.id in enum:
                    events.append(event)
                    break

        return Rack(*events, channel_count=self.channel_count)

    comments = EventProp[str](ProjectID.Comments, ProjectID._RTFComments)
    """Comments / Project description.

    !!! caution
        Very old versions of FL used to store comments in RTF (Rich Text Format).
        PyFLP makes no efforts to parse that and stores it like a normal string
        as it is. It is upto you to extract the text out of it.
    """

    @property
    def created_on(self) -> Optional[datetime.datetime]:
        """The local date and time on which this project was created.

        ???+ info "Internal representation":
            Stored as a duration in days since the Delphi epoch (30 Dec, 1899).
        """
        if ProjectID.Timestamp in self._events:
            event = cast(TimestampEvent, self._events[ProjectID.Timestamp][0])
            return DELPHI_EPOCH + datetime.timedelta(days=event["created_on"])

    format = KWProp[FileFormat]()
    """Internal format used by FL Studio to store different types of data."""

    @property
    def data_path(self) -> Optional[pathlib.Path]:
        """The absolute path used by FL to store all your renders."""
        if ProjectID.DataPath in self._events:
            event = self._events[ProjectID.DataPath][0]
            return pathlib.Path(event.value)

    @data_path.setter
    def data_path(self, value: Union[str, pathlib.Path]):
        if ProjectID.DataPath not in self._events:
            raise PropertyCannotBeSet(ProjectID.DataPath)

        if isinstance(value, pathlib.Path):
            value = str(value)

        path = "" if value == "." else value
        self._events[ProjectID.DataPath][0].value = path

    genre = EventProp[str](ProjectID.Genre)
    licensed = EventProp[bool](ProjectID.Licensed)
    """Whether the project was last saved with a licensed copy of FL Studio.

    !!! tip "Activate your FLP"
        Setting this to `True` and saving back the FLP will make it load the
        next time in a trial version of FL if it wouldn't open before.
    """

    @property
    def licensee(self) -> Optional[str]:
        """The license holder's username who last saved the project file.

        If saved with a trial version this is empty.

        !!! tip
            As of the latest version, FL doesn't check for the contents of
            this for deciding whether to open it or not when in trial version.

        ???+ info "Internal representation"
            Internally the value of this field is stored jumbled up. Thanks to
            @codecat/libflp for finding out the algorithm used.
        """
        events = self._events.get(ProjectID.Licensee)
        if events is not None:
            event = events[0]
            licensee = bytearray()
            for idx, char in enumerate(event.value):
                c1 = ord(char) - 26 + idx
                c2 = ord(char) + 49 + idx

                if str(c1).isalnum():
                    licensee.append(c1)
                elif str(c2).isalnum():
                    licensee.append(c2)

            return licensee.decode("ascii")

    @licensee.setter
    def licensee(self, value: str):
        if ProjectID.Licensee not in self._events:
            raise PropertyCannotBeSet(ProjectID.Licensee)

        event = self._events[ProjectID.Licensee][0]
        licensee = bytearray()
        for idx, char in enumerate(value):
            c1 = ord(char) + 26 - idx
            c2 = ord(char) - 49 - idx

            for c in c1, c2:
                if c > 0 and c <= 127:
                    licensee.append(c)
                    break
        event.value = licensee.decode("ascii")

    looped = EventProp[bool](ProjectID.LoopActive)
    main_pitch = EventProp[int](ProjectID.Pitch)
    main_volume = EventProp[int](ProjectID._Volume)

    @property
    def mixer(self) -> Mixer:
        return Mixer(*self._collect_events(MixerID, InsertID, SlotID))

    @property
    def patterns(self) -> Patterns:
        return Patterns(*self._collect_events(PatternsID, PatternID))

    pan_law = EventProp[PanLaw](ProjectID.PanLaw)

    @property
    def ppq(self) -> int:
        """Pulses per quarter.

        !!! info
            All types of lengths, positions and offsets internally use the PPQ
            as a multiplying factor.

        !!! danger
            Don't try to set this property, it affects all the length, position
            and offset calculations used for deciding the placement of playlist,
            automations, timemarkers and patterns.

            When you change this in FL, it recalculates all the above. It is
            beyond the PyFLP's scope to properly recalculate the timings.

        Raises:
            ExpectedValue: When a value not in `VALID_PPQS` is tried to be set.
        """
        return self._kw["ppq"]

    @ppq.setter
    def ppq(self, value: int):
        if value not in VALID_PPQS:
            raise ExpectedValue(value, VALID_PPQS)
        self._kw["ppq"] = value

    show_info = EventProp[bool](ProjectID.ShowInfo)
    """Whether to show a banner while the project is loading inside FL Studio.

    The banner shows the `title`, `artists`, `genre`, `comments` and `url`.
    """

    title = EventProp[str](ProjectID.Title)

    @property
    def tempo(self) -> Union[int, float, None]:
        """Tempo at the current position of the playhead (in BPM).

        ???+ info "Internal Representation"
            Stored as the actual BPM * 1000 as an integer.
        """
        if ProjectID.Tempo in self._events:
            return self._events[ProjectID.Tempo][0].value / 1000

        tempo = None
        if ProjectID._TempoCoarse in self._events:
            tempo = self._events[ProjectID._TempoCoarse][0].value
        if ProjectID._TempoFine in self._events:
            tempo += self._events[ProjectID._TempoFine][0].value / 1000
        return tempo

    @tempo.setter
    def tempo(self, value: Union[int, float]):
        if ProjectID.Tempo in self._events:
            self._events[ProjectID.Tempo][0].value = int(value * 1000)

        if ProjectID._TempoFine in self._events:
            tempo_fine = int((value - math.floor(value)) * 1000)
            self._events[ProjectID._TempoFine][0].value = tempo_fine

        if ProjectID._TempoCoarse in self._events:
            self._events[ProjectID._TempoCoarse][0].value = math.floor(value)

    @property
    def time_spent(self) -> Optional[datetime.timedelta]:
        """Time spent on the project since its creation.

        Technically, since the last reset via FL's interface.
        """
        if ProjectID.Timestamp in self._events:
            event = cast(TimestampEvent, self._events[ProjectID.Timestamp][0])
            return datetime.timedelta(days=event["time_spent"])

    url = EventProp[str](ProjectID.Url)

    @property
    def version(self) -> FLVersion:
        """The version of FL Studio which was used to save the file.

        !!! caution
            Changing this to a lower version will not make a file load magically
            inside FL Studio, as newer events and/or plugins might have been used.

        ???+ abstract "Internal representation"
            Internally represented as a string with a format of
            `major.minor.patch.build?` *where `build` is optional, since
            older versions of FL didn't follow the same versioning scheme*.

            To maintain backward compatibility with FL Studio versions prior
            to 11.5 whichn stored strings in ASCII, this event is always stored
            with ASCII data, even if the rest of the strings use Unicode.

        Raises:
            PropertyCannotBeSet: When the underlying event couldn't be found.
                This error should NEVER occur; if it does, it indicates possible
                corruption.
            ExpectedValue: When a string with an invalid format is tried to be set.
        """
        events = self._events[ProjectID.FLVersion]
        event = cast(AsciiEvent, events[0])
        return FLVersion(*tuple(map(int, event.value.split("."))))

    @version.setter
    def version(self, value: Union[FLVersion, str, Tuple[int, ...]]):
        if ProjectID.FLVersion not in self._events:
            raise PropertyCannotBeSet(ProjectID.FLVersion)

        if isinstance(value, FLVersion):
            parts = [value.major, value.minor, value.patch]
            if value.build is not None:
                parts.append(value.build)
        elif isinstance(value, str):
            parts = tuple(map(int, value.split(".")))
        else:
            parts = value

        if len(parts) < 3 or len(parts) > 4:
            raise ExpectedValue("Expected format: major.minor.build.patch?")

        version = ".".join(map(str, parts))
        self._events[ProjectID.FLVersion][0].value = version
        if len(parts) == 4 and ProjectID.FLBuild in self._events:
            self._events[ProjectID.FLBuild][0].value = parts[3]
