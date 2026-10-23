"""Learn task context, return values, and workspace paths without a solver.

Run with ``python examples/workflows/workflow_basics.py``.
The workflow also supports remote submission; see the website workflow guide.
"""

import femora as fm


# --8<-- [start:input]
def write_base_value(context):
    path = context.output_dir / "base_value.txt"
    path.write_text(str(context.inputs["base_value"]), encoding="utf-8")
    return path
# --8<-- [end:input]


# --8<-- [start:calculate]
def calculate(context, factor):
    input_file = context.result("prepare", "write_base_value")
    number = float(input_file.read_text(encoding="utf-8"))
    value = number * factor
    path = context.output_dir / "value.txt"
    path.write_text(str(value), encoding="utf-8")
    return value
# --8<-- [end:calculate]


# --8<-- [start:report]
def write_report(context):
    doubled = context.result("calculate", "double")
    tripled = context.result("calculate", "triple")
    path = context.output_dir / "summary.txt"
    path.write_text(
        f"double: {doubled}\ntriple: {tripled}\n", encoding="utf-8"
    )
    return path
# --8<-- [end:report]


# --8<-- [start:workflow]
def build_workflow():
    workflow = fm.Workflow("workflow-basics")
    workflow.add("prepare", tasks=[fm.tasks.Python("write_base_value", write_base_value)])
    workflow.add(
        "calculate",
        tasks=[
            fm.tasks.Python("double", calculate, kwargs={"factor": 2}),
            fm.tasks.Python("triple", calculate, kwargs={"factor": 3}),
        ],
    )
    workflow.add("report", tasks=[fm.tasks.Python("write_summary", write_report)])
    workflow.outputs("report/write_summary/summary.txt", "calculate/*/value.txt")
    return workflow
# --8<-- [end:workflow]


# --8<-- [start:execute]
if __name__ == "__main__":
    run = fm.execute(
        build_workflow(),
        workspace="example_outputs/workflow_basics",
        inputs={"base_value": 4},
        cores=1,
    )
    print(run.result("report", "write_summary").read_text(encoding="utf-8"))
# --8<-- [end:execute]
