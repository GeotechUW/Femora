"""A small executable example of ordered stages and parallel Python tasks.

Run with ``python examples/workflows/local_parallel_stages.py``.
"""

from pathlib import Path

import femora as fm


def calculate(ctx):
    value = ctx.inputs["value"]
    (ctx.output_dir / "value.txt").write_text(str(value * value), encoding="ascii")
    return value * value


def summarize(ctx):
    values = [ctx.result("calculate", name) for name in ("first", "second")]
    output = ctx.output_dir / "summary.txt"
    output.write_text(f"sum of squares: {sum(values)}\n", encoding="ascii")
    return sum(values)


if __name__ == "__main__":
    workflow = fm.Workflow("local-example")
    workflow.add(
        "calculate",
        parallel=True,
        tasks=[fm.tasks.Python("first", calculate), fm.tasks.Python("second", calculate)],
    )
    workflow.add("summary", tasks=[fm.tasks.Python("write", summarize)])
    workflow.outputs("summary/**/*.txt")

    run = fm.execute(workflow, workspace=Path("example_outputs/workflow_local"), inputs={"value": 3})
    print(f"Summary: {run.result('summary', 'write')}")
    print(f"Manifest: {run.manifest}")
