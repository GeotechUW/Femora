"""Structure-aware response interpretation layered over format-neutral results."""
from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np

from .exceptions import ResultFormatError, UnsupportedResultOperation
from .result_set import open_results


def write_building_metadata(path, metadata):
    """Explicitly write a compact, versioned structural index, without histories."""
    with h5py.File(path, "w") as target:
        target.attrs["schema"] = "femora.building"
        target.attrs["version"] = 1
        for name, value in metadata.items():
            if isinstance(value, np.ndarray):
                target.create_dataset(name, data=value, compression="gzip")
            else:
                encoded = np.frombuffer(json.dumps(value, allow_nan=False).encode("utf-8"), dtype=np.uint8)
                dataset = target.create_dataset(name, data=encoded, compression="gzip")
                dataset.attrs["encoding"] = "json-utf8"


def read_building_metadata(path):
    """Read only explicitly requested metadata; never search for sidecar files."""
    with h5py.File(path, "r") as source:
        if source.attrs.get("schema") != "femora.building" or source.attrs.get("version") != 1:
            raise ResultFormatError("Unsupported building metadata schema/version")
        metadata = {name: (json.loads(source[name][()].tobytes().decode("utf-8"))
                           if source[name].attrs.get("encoding") == "json-utf8" else source[name][()])
                    for name in source}
        metadata.update({name: json.loads(value) for name, value in source.attrs.items()
                         if name not in {"schema", "version"}})
    return metadata


class BuildingResults:
    """Interpret recorded responses using explicit building membership metadata.

    Wraps a ResultSet; geometry is used to verify identities, never to
    guess member roles. No files are created until ``export_csv()`` is called.
    Every response method returns a pandas DataFrame with units and basis in
    ``attrs``. Missing recorded fields raise ``UnsupportedResultOperation``.

    Example:
        ```python
        from femora.results import BuildingResults

        with BuildingResults.open(
            "results/building*.vtkhdf", metadata="building.structure.h5",
        ) as results:
            drift = results.interstory_drift(direction="x")
            forces = results.member_forces(kind="brace", end="both")
            results.export_csv("processed", responses=["interstory_drift"])
        ```

    Note:
        Member forces are element-end actions, not fiber stresses or failure
        assessments. Story/base shear is a signed element-force cut resultant,
        not an inertia-based estimate. Global-end moments and force lever arms
        are included in overturning moments. Units are supplied by the caller's
        metadata; the reader performs no unit conversion.

        Floor quantities are arithmetic averages of structural-joint translations,
        not mass-weighted center-of-mass values. In SSI, relative-to-base motion
        removes translation only, not foundation rocking. No failure criterion
        is inferred from member forces or drift.
    """

    __doc_controls__ = {"summary": True, "members": [
        "open", "members", "floor_displacement", "floor_acceleration",
        "interstory_drift", "member_forces", "story_shear", "base_shear",
        "overturning_moment", "summary", "export_csv", "close",
    ]}

    def __init__(self, raw, metadata):
        self.raw = raw
        self.metadata = metadata
        self._nodes = {}
        self._elements = {}
        self._coordinates = dict(zip(map(int, metadata["node_tags"]), metadata["coordinates"]))
        self._connectivity = dict(zip(map(int, metadata["element_tags"]), metadata["connectivity"]))
        if (len(self._coordinates) != len(metadata["node_tags"])
                or len(self._connectivity) != len(metadata["element_tags"])
                or np.asarray(metadata["coordinates"]).shape != (len(self._coordinates), 3)
                or np.asarray(metadata["connectivity"]).shape != (len(self._connectivity), 2)
                or not np.isfinite(metadata["coordinates"]).all()
                or np.any(np.diff(metadata["floor_elevations"]) <= 0)
                or len(metadata["floor_nodes"]) != len(metadata["floor_elevations"])
                or any(not nodes or not set(nodes).issubset(self._coordinates) for nodes in metadata["floor_nodes"])):
            raise ResultFormatError("Invalid building identities, coordinates, connectivity, or floors")
        member_elements = [tag for member in metadata["members"] for tag in member["elements"]]
        if len(set(member_elements)) != len(member_elements) or set(member_elements) != set(self._connectivity):
            raise ResultFormatError("Each structural element must belong to exactly one physical member")
        if any(not np.isclose(self._coordinates[int(tag)][2], z, rtol=0, atol=1e-7)
               for z, nodes in zip(metadata["floor_elevations"], metadata["floor_nodes"]) for tag in nodes):
            raise ResultFormatError("Floor assignments disagree with node elevations")
        if raw.times is None or not np.isfinite(raw.times).all() or np.any(np.diff(raw.times) < 0):
            raise ResultFormatError("Building responses require finite, ordered recorder samples")
        self._bind()

    @classmethod
    def open(cls, source, *, metadata) -> BuildingResults:
        """Open result files with a metadata mapping or explicit metadata path.

        Args:
            source (str | Path | list): VTKHDF path, glob, or partition paths.
            metadata (dict | str | Path): Structural index from the live building, or path explicitly
                written using ``building.export_metadata(model, path)``.

        Returns:
            BuildingResults: Owns its underlying readers. Close it or use it
                as a context manager. No building reconstruction is needed.

        Raises:
            FileNotFoundError: Recorder or metadata files cannot be found.
            ResultFormatError: Metadata schema, node identities, connectivity,
                floor assignments, or partition timestamps are inconsistent.

        Note:
            Metadata and recorder files must come from the same assembled model.
            Include every partition containing building members. Coincident
            nodes/elements require unambiguous recorded nodeTags/eleTags.
    """
        if isinstance(metadata, (str, Path)):
            metadata = read_building_metadata(metadata)
        raw = open_results(source)
        try:
            return cls(raw, metadata)
        except Exception:
            raw.close()
            raise

    def _bind(self):
        by_coordinate = {}
        for tag, coordinate in self._coordinates.items():
            by_coordinate.setdefault(tuple(np.round(coordinate, 8)), []).append(tag)
        by_connection = {}
        for tag, nodes in self._connectivity.items():
            by_connection.setdefault(tuple(sorted(map(int, nodes))), []).append(tag)
        for partition, reader in enumerate(self.raw.readers):
            mesh = reader.mesh
            point_tags = None
            if "nodeTags" in reader.available_point_responses:
                point_tags = reader.point_frame("nodeTags", 0).reshape(-1)
            elif "nodeTags" in mesh.point_data:
                point_tags = mesh.point_data["nodeTags"].reshape(-1)
            resolved = {}
            resolved_tags = set()
            for index, point in enumerate(mesh.points):
                if point_tags is None:
                    candidates = by_coordinate.get(tuple(np.round(point, 8)), [])
                    if len(candidates) > 1:
                        raise ResultFormatError("Coincident building nodes require nodeTags in VTKHDF; coordinate matching is ambiguous")
                    tag = candidates[0] if candidates else None
                else:
                    tag = int(point_tags[index])
                if tag not in self._coordinates:
                    continue
                if not np.allclose(point, self._coordinates[tag], rtol=0, atol=1e-7):
                    raise ResultFormatError(f"Metadata/result coordinates disagree for node {tag}")
                if tag in resolved_tags:
                    raise ResultFormatError("Repeated/coincident node identity in one partition requires unambiguous nodeTags")
                resolved[index] = tag
                resolved_tags.add(tag)
                self._nodes.setdefault(tag, []).append((partition, index))
            cell_tags = None
            if "eleTags" in reader.available_cell_responses:
                cell_tags = reader.cell_frame("eleTags", 0).reshape(-1)
            elif "eleTags" in mesh.cell_data:
                cell_tags = mesh.cell_data["eleTags"].reshape(-1)
            for index in range(mesh.n_cells):
                cell = mesh.get_cell(index)
                if len(cell.point_ids) != 2 or any(int(i) not in resolved for i in cell.point_ids):
                    continue
                nodes = tuple(resolved[int(i)] for i in cell.point_ids)
                if cell_tags is None:
                    candidates = by_connection.get(tuple(sorted(nodes)), [])
                    if len(candidates) > 1:
                        raise ResultFormatError("Parallel/coincident elements require eleTags in VTKHDF")
                    tag = candidates[0] if candidates else None
                else:
                    tag = int(cell_tags[index])
                if tag not in self._connectivity:
                    continue
                if nodes != tuple(map(int, self._connectivity[tag])):
                    raise ResultFormatError(f"Metadata/result connectivity or end order disagrees for element {tag}")
                self._elements.setdefault(tag, []).append((partition, index))
        missing_nodes = set(self._coordinates) - self._nodes.keys()
        missing_elements = set(self._connectivity) - self._elements.keys()
        if missing_nodes or missing_elements:
            raise ResultFormatError(f"Result mesh is missing {len(missing_nodes)} building nodes and {len(missing_elements)} elements")

    def _history(self, tag, response, *, cell=False):
        entries = (self._elements if cell else self._nodes)[int(tag)]
        values = []
        for partition, index in entries:
            reader = self.raw.readers[partition]
            available = reader.available_cell_responses if cell else reader.available_point_responses
            if response not in available:
                raise UnsupportedResultOperation(f"Recorded field '{response}' is missing in {reader.path.name}; request it in get_recorders() and use a supporting OpenSees binary")
            method = reader.cell_history if cell else reader.point_history
            values.append(np.asarray(method(response, index)))
        if any(value.shape != values[0].shape or not np.allclose(value, values[0], rtol=1e-8, atol=1e-10)
               for value in values[1:]):
            raise ResultFormatError(f"Conflicting partition copies of entity {tag}")
        if not np.isfinite(values[0]).all():
            raise ResultFormatError(f"Nonfinite {response} history for entity {tag}")
        return values[0]

    def _frame(self, values, columns, *, units, basis="recorded"):
        import pandas as pd
        frame = pd.DataFrame(values, columns=columns,
                             index=pd.Index(self.raw.times, name=self.metadata.get("abscissa", "time_s")))
        frame.attrs.update(units=units, basis=basis)
        return frame

    @staticmethod
    def _direction(direction):
        if direction not in {"x", "y", "z"}:
            raise ValueError("direction must be x, y, or z")
        return "xyz".index(direction)

    def _floors(self, response, direction):
        component = self._direction(direction)
        return np.column_stack([
            np.mean([self._history(tag, response)[:, component] for tag in nodes], axis=0)
            for nodes in self.metadata["floor_nodes"]])

    def members(self):
        """Inspect physical-member identities before selecting force histories.

        Returns:
            table (pandas.DataFrame): Physical-member index and metadata columns,
                such as kind, story, section, and element tags. A subdivided
                beam is one physical member with several finite elements.

        Example:
            ```python
            catalogue = results.members()
            braces = catalogue[catalogue["kind"] == "brace"]
            forces = results.member_forces(member_ids=braces.index.tolist())
            ```
        """
        import pandas as pd
        return pd.DataFrame(self.metadata["members"]).set_index("member")

    def floor_displacement(self, direction="x", *, relative_to_base=False, include_base=False):
        """Return mean structural-joint floor translations, not mass-weighted means.

        ``relative_to_base=True`` subtracts the recorded base translation at
        each sample. Gravity offsets are not silently removed.

        Args:
            direction (str): Global ``"x"``, ``"y"``, or ``"z"``.
            relative_to_base (bool): Subtract the mean translation of floor 0. This
                does not remove the displacement caused by foundation rotation.
            include_base (bool): Include floor 0; otherwise return floors 1 through N.

        Returns:
            table (pandas.DataFrame): Recorder-sample index, integer floor columns, and
                metadata length units in attrs. The base-relative floor-0
                column is zero if both options are enabled.

        Raises:
            ValueError: Direction is unsupported.
            UnsupportedResultOperation: Displacement was not recorded.
            ResultFormatError: A history is nonfinite or partition copies conflict.

        Example:
            ```python
            floors = results.floor_displacement("x", relative_to_base=True)
            roof = floors.iloc[:, -1]
            ```
        """
        values = self._floors("displacement", direction)
        if relative_to_base:
            values = values-values[:, :1]
        first = 0 if include_base else 1
        return self._frame(values[:, first:], list(range(first, values.shape[1])),
                           units=self.metadata["units"]["length"],
                           basis="relative_to_base" if relative_to_base else "recorded")

    def floor_acceleration(self, direction="x", *, basis="recorded", ground_motion=None, include_base=False):
        """Return floor acceleration with explicit relative/absolute conversion.

        For conversion, supply ``ground_motion=(time, acceleration)`` with a
        scalar component or an N-by-3 array, or a DataFrame indexed by time with
        x/y/z columns. Its times must cover all recorder times, including any
        free-vibration tail, and its acceleration units must match the results.
        No motion is guessed from a filename and no scaling is applied.

        Args:
            direction (str): Global ``"x"``, ``"y"``, or ``"z"``.
            basis (str): ``"recorded"`` (default), ``"absolute"``, or ``"relative"``.
                If the requested basis already matches metadata, no conversion occurs.
            ground_motion (tuple | pandas.DataFrame | None): Motion for basis conversion;
                see the accepted forms above. Components are in global axes.
            include_base (bool): Include the base-floor mean acceleration if True.

        Returns:
            table (pandas.DataFrame): Floor columns, recorder-sample index, and
                acceleration units and resulting basis in attrs.

        Raises:
            UnsupportedResultOperation: Acceleration is absent, or conversion
                lacks a declared recorded basis and explicit ground motion.
            ValueError: Basis, direction, or supplied motion samples are invalid.

        Examples:
            DRM output already declared absolute needs no added ground motion:

            ```python
            acceleration = results.floor_acceleration("x", basis="absolute")
            ```

            For metadata declared relative under uniform excitation:

            ```python
            acceleration = results.floor_acceleration(
                "x", basis="absolute", ground_motion=(motion_time, ground_ax),
            )
            ```
        """
        values = self._floors("acceleration", direction)
        recorded = self.metadata.get("acceleration_basis", "unspecified")
        if basis not in {"recorded", "relative", "absolute"}:
            raise ValueError("basis must be recorded, relative, or absolute")
        if basis != "recorded" and basis != recorded:
            if recorded not in {"relative", "absolute"} or ground_motion is None:
                raise UnsupportedResultOperation("Conversion requires a declared recorded acceleration basis and explicit ground_motion")
            if hasattr(ground_motion, "index") and hasattr(ground_motion, "columns"):
                time, motion = np.asarray(ground_motion.index), np.asarray(ground_motion[direction])
            else:
                time, motion = map(np.asarray, ground_motion)
                if motion.ndim == 2:
                    motion = motion[:, self._direction(direction)]
            if (time.ndim != 1 or motion.shape != time.shape or len(time) < 2
                    or not np.isfinite(time).all() or not np.isfinite(motion).all()
                    or np.any(np.diff(time) <= 0) or time[0] > self.raw.times[0]
                    or time[-1] < self.raw.times[-1]):
                raise ValueError("Ground motion must be finite, increasing, and cover all recorded times")
            sign = 1 if basis == "absolute" else -1
            values = values + sign*np.interp(self.raw.times, time, motion)[:, None]
        first = 0 if include_base else 1
        return self._frame(values[:, first:], list(range(first, values.shape[1])),
                           units=self.metadata["units"].get("acceleration", "model_acceleration_units"),
                           basis=recorded if basis == "recorded" else basis)

    def interstory_drift(self, direction="x"):
        """Calculate signed translation-based drift ratios for every story.

        Args:
            direction (str): Global ``"x"``, ``"y"``, or ``"z"``. Horizontal x/y
                components are normally used for lateral interstory drift.

        Returns:
            table (pandas.DataFrame): Story columns 1 through N. Each value is
                (upper mean translation - lower mean translation) / story height.
                Values are dimensionless ratios, not percentages; multiply by 100
                for percent. Story 1 uses the recorded base as its lower floor.

        Raises:
            UnsupportedResultOperation: Displacement was not recorded.

        Note:
            Neither foundation rocking nor floor torsional variation is removed.
            These mean-floor ratios are not maximum corner drifts or a design
            acceptance check.

        Example:
            ```python
            drift_percent = 100 * results.interstory_drift("x")
            peak_by_story = drift_percent.abs().max()
            ```
        """
        values = np.diff(self._floors("displacement", direction), axis=1)/np.diff(self.metadata["floor_elevations"])
        return self._frame(values, list(range(1, values.shape[1]+1)), units="ratio", basis="relative_floor_motion")

    def member_forces(self, kind="all", *, coordinate_system="global", end="both", story=None, member_ids=None):
        """Return recorded end forces with (member, element, end, component) columns.

        ``kind`` is beam, column, brace, or all. End i/j follows the exported
        element connectivity. Moments and forces use their respective metadata
        units. This is not a yield or failure assessment.
        Use ``story`` or ``member_ids`` to restrict large queries without
        loading histories for unrelated members.

        Args:
            kind (str): ``"beam"``, ``"column"``, ``"brace"``, or ``"all"``.
            coordinate_system (str): ``"global"`` requests force3D; ``"local"``
                requests localForce3D. Local axes follow the exported element.
            end (str): ``"i"``, ``"j"``, or ``"both"``; connectivity defines end order.
            story (int | None): One story number, or None for every story.
            member_ids (Iterable[int] | None): Physical IDs from members(), or None for all.

        Returns:
            table (pandas.DataFrame): Four-level columns: member, element, end, component.
                Components are Fx, Fy, Fz, Mx, My, Mz. Empty selections return zero
                columns. Force and moment units are in attrs.

        Raises:
            ValueError: Kind, coordinate system, or end is invalid.
            UnsupportedResultOperation: The selected force field was not recorded.
            ResultFormatError: End-force fields do not contain 12 components.

        Example:
            ```python
            brace_forces = results.member_forces(
                kind="brace", story=1, coordinate_system="local", end="i",
            )
            ```
        """
        import pandas as pd
        if coordinate_system not in {"global", "local"} or end not in {"i", "j", "both"}:
            raise ValueError("Use global/local coordinates and i/j/both ends")
        if kind not in {"beam", "column", "brace", "all"}:
            raise ValueError("kind must be beam, column, brace, or all")
        columns, values = [], []
        for member in self.metadata["members"]:
            if kind != "all" and member["kind"] != kind:
                continue
            if story is not None and member["story"] != story:
                continue
            if member_ids is not None and member["member"] not in member_ids:
                continue
            for tag in member["elements"]:
                data = self._history(tag, "force3D" if coordinate_system == "global" else "localForce3D", cell=True)
                if data.shape != (self.raw.number_of_steps, 12):
                    raise ResultFormatError("3D element end forces must have 12 components")
                for side, offset in (("i", 0), ("j", 6)):
                    if end != "both" and side != end:
                        continue
                    for component, label in enumerate(("Fx", "Fy", "Fz", "Mx", "My", "Mz")):
                        columns.append((member["member"], tag, side, label))
                        values.append(data[:, offset+component])
        index = pd.MultiIndex.from_tuples(columns, names=["member", "element", "end", "component"])
        return self._frame(np.column_stack(values) if values else np.empty((self.raw.number_of_steps, 0)), index,
                           units={"force": self.metadata["units"]["force"], "moment": self.metadata["units"]["moment"]},
                           basis=coordinate_system)

    def _cut(self, elevation, reference):
        resultant = np.zeros((self.raw.number_of_steps, 6))
        found = False
        for tag, nodes in self._connectivity.items():
            points = np.asarray([self._coordinates[int(node)] for node in nodes])
            low = int(np.argmin(points[:, 2]))
            if not (points[low, 2] <= elevation+1e-8 and points[1-low, 2] > elevation+1e-8):
                continue
            found = True
            forces = self._history(tag, "force3D", cell=True)
            if forces.shape[1] != 12:
                raise ResultFormatError("force3D must have 12 end components")
            end = forces[:, low*6:low*6+6]
            resultant[:, :3] -= end[:, :3]
            resultant[:, 3:] -= end[:, 3:] + np.cross(points[low]-reference, end[:, :3])
        if not found:
            raise UnsupportedResultOperation(f"No structural members cross the requested cut at elevation {elevation}")
        return resultant

    def story_shear(self, direction="x"):
        """Return negative lower-end global force sums at each floor-bottom cut.

        All structural members crossing the cut contribute, including braces.
        Subdivided physical members contribute only the segment crossing it.
        These are resisting-force resultants, not sums of nodal inertia.

        Args:
            direction (str): Global ``"x"``, ``"y"``, or ``"z"`` force component.

        Returns:
            table (pandas.DataFrame): Story columns 1 through N, in metadata force units.
                A cut is placed at each story's lower-floor elevation.

        Raises:
            UnsupportedResultOperation: Global force3D is unavailable or no
                structural members cross a requested cut.
            ResultFormatError: Force arrays have an invalid component count.

        Note:
            A positive result is the negative sum of lower-end actions in the
            selected global direction. It is not a support-reaction sum.
        """
        component = self._direction(direction)
        values = [self._cut(z, np.asarray(self.metadata["moment_reference"]))[:, component]
                  for z in self.metadata["floor_elevations"][:-1]]
        return self._frame(np.column_stack(values), list(range(1, len(values)+1)), units=self.metadata["units"]["force"])

    def base_shear(self, direction="x"):
        """Read the first-story force-cut resultant at the building base.

        Args:
            direction (str): Global ``"x"``, ``"y"``, or ``"z"`` force component.

        Returns:
            table (pandas.DataFrame): One column, ``"base"``, using the same force units
                and sign convention as story_shear().

        Raises:
            UnsupportedResultOperation: Required global end forces are missing
                or no building members cross the base cut.

        Note:
            In SSI this is the building's base cut, not the soil boundary reaction
            or total foundation/pile force. Unsupported solver force responses
            can contain zeros; zeros alone do not demonstrate zero demand.
        """
        frame = self.story_shear(direction).iloc[:, :1].copy()
        frame.columns = ["base"]
        return frame

    def overturning_moment(self, axis="y", *, reference=None):
        """Return base moment including global end moments and force lever arms.

        Reference defaults to the plan center at base elevation. Supply a
        global XYZ point to choose a different moment reference.

        Args:
            axis (str): Global moment axis, ``"x"``, ``"y"``, or ``"z"``. About y
                is the default; this differs from a lateral-load direction.
            reference (Sequence[float] | None): Global XYZ reference in model length units.

        Returns:
            table (pandas.DataFrame): One ``"base"`` column in metadata moment units.
                Includes both end moments and r cross F contributions.

        Raises:
            ValueError: Reference point or axis is invalid.
            UnsupportedResultOperation: Required force histories are absent.
        """
        component = self._direction(axis)+3
        point = np.asarray(self.metadata["moment_reference"] if reference is None else reference, dtype=float)
        if point.shape != (3,) or not np.isfinite(point).all():
            raise ValueError("reference must be a finite XYZ point")
        values = self._cut(self.metadata["floor_elevations"][0], point)[:, component]
        return self._frame(values[:, None], ["base"], units=self.metadata["units"]["moment"])

    def summary(self, *, responses=None, direction="x"):
        """Return peak magnitudes and their recorded sample coordinates.

        Defaults summarize displacement and drift, plus acceleration if present.
        Request force-derived responses explicitly; absent force fields raise
        an error rather than producing a misleading zero-demand summary.

        Args:
            responses (Iterable[str] | None): Names selected from floor_displacement,
                floor_acceleration, interstory_drift, story_shear, base_shear,
                overturning_moment, and member_forces. None uses the defaults above.
            direction (str): Global component for floor/drift/shear queries; moment
                axis for overturning_moment. Member forces retain all components.

        Returns:
            table (pandas.DataFrame): Response, entity, direction, peak_abs, signed_value,
                sample, units, and basis columns. Sample is the recorded coordinate
                at the absolute peak, not necessarily seconds. Tied peaks use
                the first sample.

        Example:
            ```python
            peaks = results.summary(
                responses=["interstory_drift", "base_shear"], direction="x",
            )
            peaks.to_csv("peaks_x.csv", index=False)
            ```

        Note:
            Summary floor displacement uses recorded motion, not automatically
            base-relative motion. No threshold or pass/fail assessment is applied.
        """
        import pandas as pd
        if responses is None:
            responses = ["floor_displacement", "interstory_drift"]
            if "acceleration" in self.raw.available_point_responses:
                responses.append("floor_acceleration")
        records = []
        for response in responses:
            frame = self._response(response, direction)
            for column in frame:
                values = frame[column].to_numpy()
                index = int(np.argmax(np.abs(values)))
                units = frame.attrs["units"]
                if isinstance(units, dict) and isinstance(column, tuple):
                    units = units["moment" if str(column[-1]).startswith("M") else "force"]
                records.append(dict(response=response, entity=column, direction=direction,
                                    peak_abs=float(abs(values[index])), signed_value=float(values[index]),
                                    sample=float(frame.index[index]), units=units, basis=frame.attrs["basis"]))
        return pd.DataFrame(records)

    def _response(self, response, direction):
        allowed = {"floor_displacement", "floor_acceleration", "interstory_drift", "story_shear", "base_shear",
                   "overturning_moment", "member_forces"}
        if response not in allowed:
            raise ValueError(f"Response must be one of {sorted(allowed)}")
        if response == "overturning_moment":
            return self.overturning_moment(axis=direction)
        if response == "member_forces":
            return self.member_forces()
        return getattr(self, response)(direction=direction)

    def export_csv(self, directory, *, responses, direction="x"):
        """Explicitly export selected histories and return their paths.

        Files are named response_direction.csv. No response files are written
        by construction, get_results(), or individual response queries.

        Args:
            directory (str | Path): Output directory; created if missing. Existing files
                with matching response/direction names are overwritten.
            responses (Iterable[str]): Response names accepted by summary(). All
                requested tables are evaluated before any output is written.
            direction (str): Global component, or moment axis for overturning_moment.
                Member forces use their default all-member/global/both-end query.

        Returns:
            paths (list[Path]): Written files. Each CSV includes the recorded sample
                index and uses the method's default response options.

        Raises:
            ValueError: An unknown response or direction is requested.
            UnsupportedResultOperation: A required field is missing.
            OSError: Output paths cannot be created or written.

        Note:
            CSV does not preserve DataFrame attrs. To export custom options such
            as base-relative translation, call that method and use to_csv() on
            its returned table instead.

        Example:
            ```python
            results.export_csv(
                "processed", responses=["interstory_drift", "base_shear"],
                direction="x",
            )
            results.floor_displacement("x", relative_to_base=True).to_csv(
                "processed/base_relative_x.csv",
            )
            ```
        """
        # Evaluate first so a missing response cannot leave a partial export.
        frames = {name: self._response(name, direction) for name in responses}
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for name, frame in frames.items():
            path = directory / f"{name}_{direction}.csv"
            frame.to_csv(path)
            paths.append(path)
        return paths

    def close(self):
        """Close owned result readers."""
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
