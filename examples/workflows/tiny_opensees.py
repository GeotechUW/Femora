"""Build and run two one-element Femora cantilevers with different stiffnesses.

Set FEMORA_OPENSEES to an OpenSees executable (or put it on PATH), then run
``python examples/workflows/tiny_opensees.py``. Use ``--bundle tiny.zip`` to
package this same file for replay with ``python -m femora.jobs replay tiny.zip
--workspace example_outputs/tiny_replay --cores 2``. Each solve is serial; the
two independent models run concurrently in separate processes.
"""

import argparse
from pathlib import Path

import femora as fm


LENGTH = 1.0
TIP_LOAD = -1000.0
SECOND_MOMENT = 1.0e-4
DEFAULT_INPUTS = {"moduli": {"soft": 2.0e9, "stiff": 4.0e9}}


def create_model(ctx):
    name = ctx.output_dir.name
    modulus = ctx.inputs["moduli"][name]
    script = ctx.workspace / "models" / f"{name}.tcl"
    script.parent.mkdir(parents=True, exist_ok=True)
    result_dir = ctx.workspace / "solve" / name

    model = fm.Model(model_name=f"tiny_cantilever_{name}", model_path=str(ctx.output_dir))
    model.set_results_folder(result_dir.resolve().as_posix())
    section = model.section.beam.elastic(
        user_name="beam_section",
        E=modulus,
        A=0.04,
        Iz=SECOND_MOMENT,
        Iy=SECOND_MOMENT,
        G=modulus / 2.6,
        J=2.0e-4,
    )
    transformation = model.transformation.transformation3d(
        transf_type="Linear", vecxz_x=0.0, vecxz_y=0.0, vecxz_z=1.0
    )
    beam = model.element.beam.elastic(
        ndof=6, section=section, transformation=transformation
    )
    model.meshpart.line.single_line(
        user_name="beam",
        element=beam,
        x0=0.0,
        y0=0.0,
        z0=0.0,
        x1=LENGTH,
        y1=0.0,
        z1=0.0,
        number_of_lines=1,
    )
    model.assembler.create_section(["beam"], num_partitions=0, merge_points=True)
    model.assembler.assemble(merge_points=True, progress_callback=lambda *_: None)
    model.constraint.sp.fix_x(xCoordinate=0.0, dofs=[1] * 6, tol=1.0e-9)
    tip = model.mask.nodes.near_point(point=(LENGTH, 0.0, 0.0), radius=1.0e-9)
    if len(tip) != 1:
        raise RuntimeError(f"Expected one cantilever tip node, found {len(tip)}")

    history = model.time_series.linear(factor=1.0)
    load = model.pattern.plain(time_series=history)
    load.add_load.node(node_mask=tip, values=[0.0, 0.0, TIP_LOAD, 0.0, 0.0, 0.0])
    recorder = model.recorder.node(
        file_name=(result_dir / "tip_displacement.out").resolve().as_posix(),
        nodes=tip.to_tags(),
        dofs=[3],
        resp_type="disp",
        time=True,
        precision=12,
    )
    analysis = model.analysis.static(
        name="tip_load",
        constraint_handler=model.analysis.constraint.transformation(),
        numberer=model.analysis.numberer.rcm(),
        system=model.analysis.system.bandgeneral(),
        algorithm=model.analysis.algorithm.linear(),
        test=model.analysis.test.normunbalance(tol=1.0e-10, max_iter=10),
        integrator=model.analysis.integrator.loadcontrol(incr=1.0),
        num_steps=1,
    )
    model.process.add_step(load, "Apply the tip load")
    model.process.add_step(recorder, "Record the tip displacement")
    model.process.add_step(analysis, "Run the static analysis")
    model.export_to_tcl(filename=str(script.resolve()), progress_callback=lambda *_: None)
    return script


def compare(ctx):
    values = {}
    for name in ctx.inputs["moduli"]:
        solve = ctx.result("solve", name)
        lines = (solve.output_dir / "tip_displacement.out").read_text().splitlines()
        values[name] = float(lines[-1].split()[-1])
        expected = TIP_LOAD * LENGTH**3 / (3.0 * ctx.inputs["moduli"][name] * SECOND_MOMENT)
        if abs(values[name] - expected) > abs(expected) * 0.01:
            raise RuntimeError(f"{name} displacement {values[name]} differs from {expected}")
    summary = ctx.output_dir / "comparison.txt"
    summary.write_text(
        "".join(f"{name}: {value:.9f}\n" for name, value in values.items()),
        encoding="ascii",
    )
    return values


def build_workflow(inputs=None):
    inputs = inputs or DEFAULT_INPUTS
    names = tuple(inputs["moduli"])
    if not names:
        raise ValueError("at least one modulus is required")
    workflow = fm.Workflow("tiny-opensees")
    workflow.add(
        "create",
        tasks=[fm.tasks.Python(name, create_model) for name in names],
    )
    workflow.add(
        "solve",
        parallel=True,
        tasks=[
            fm.tasks.OpenSees(name, f"models/{name}.tcl")
            for name in names
        ],
    )
    workflow.add("compare", tasks=[fm.tasks.Python("summary", compare)])
    workflow.outputs(
        "models/*.tcl",
        "solve/**/tip_displacement.out",
        "solve/**/stdout.log",
        "compare/**/*.txt",
    )
    return workflow


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, help="write a portable workflow zip")
    args = parser.parse_args()
    inputs = DEFAULT_INPUTS
    if args.bundle:
        print(fm.jobs.bundle(source=__file__, destination=args.bundle, inputs=inputs, overwrite=True))
        raise SystemExit(0)
    run = fm.execute(
        build_workflow(inputs),
        workspace=Path("example_outputs/workflow_tiny_opensees"),
        inputs=inputs,
        cores=2,
    )
    print(run.result("compare", "summary"))
    print(f"Manifest: {run.manifest}")
