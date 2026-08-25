---
title: Loads, Time Series, and Patterns
icon: material/waveform
---

# Loads, Time Series, and Patterns

Applying static or dynamic excitations to your model requires coordinating what forces are applied, how they vary over time, and when they are active. Femora organizes this using Loads, Time Series, and Patterns.

---

## Mental Model

* **Loads**: The physical force, moment, or displacement vector applied to a node or element (e.g., a nodal load of 100 kN).
* **Time Series**: Mathematical functions that define how load magnitude changes over time (e.g. constant, linear, sinusoidal, or a custom earthquake acceleration record).
* **Patterns**: Logical groupings of loads and time series that are applied together during a solver step (e.g. gravity loads, wind loads, or uniform ground motion).

This separation allows you to swap loading conditions easily. For example, you can apply static gravity loads (using a constant time series) and subsequently apply dynamic seismic excitations (using an earthquake acceleration time series) on the same assembled model without altering the physical mesh.

---

## Where It Fits

Loads, Time Series, and Patterns are defined after assembly is compiled. They are then added to the process manager to determine the execution sequence:

```text
Run Assembly
  └─ Define Time Series (e.g. Path acceleration record)
       └─ Define Load Pattern (e.g. Uniform Base Excitation)
            └─ Add Pattern to Process Step
                 └─ Run Analysis Step (Static or Transient solver run)
```

---

## Minimal Example

Defining a dynamic earthquake excitation using a time series path and a uniform excitation pattern:

```python
from femora.core.model import Model

model = Model()

# (Configure and compile assembly here...)

# 1. Define a time series pointing to a seismic record
seismic_motion = model.time_series.path(
    name="seismic_motion",
    filepath="eq_record.acc",
    dt=0.01,
    factor=9.81  # Convert to m/s^2
)

# 2. Create a base excitation pattern using the time series
earthquake_pattern = model.pattern.uniform_excitation(
    name="earthquake_pattern",
    direction=1,  # X translation
    time_series=seismic_motion
)

# 3. Add the pattern to the process manager
model.process.add_step(earthquake_pattern, description="Apply seismic loading")
```

For a list of time-series formats and pattern types, refer to the [Pattern Manager API Reference](../reference/core/pattern_manager.md) and [TimeSeriesManager API Reference](../reference/core/time_series_manager.md).

---

## What Femora Stores

For loading, Femora tracks:
- **Time Series**: Name, record file path, time increment (`dt`), and amplitude scale factors.
- **Patterns**: Unique tag, direction parameters, and associated time-series links.
- **Process Step Links**: Ordered references in the `ProcessManager` steps.

---

## Advanced Loading: Domain Reduction Method (DRM)

???+ tip "Domain Reduction Method (DRM) Loading"
    For advanced geoseismic modeling, Femora supports the **Domain Reduction Method (DRM)** as a specialized loading pattern. 
    
    Instead of applying uniform accelerations to the entire base, you can register an HDF5-based DRM pattern (`model.pattern.h5drm`). During assembly, Femora matches boundary nodes with coordinates in the HDF5 file and maps the three-dimensional seismic wave force fields directly onto the boundary elements automatically.

---

## Common Mistakes

???+ warning "Defining Loads Outside a Pattern"
    Loads or base excitations defined in isolation have no effect on the simulation. Every load vector and time series must be bound within a **Load Pattern**, and that pattern must be added to a process step to be output to the solver.

---

## Related Concepts

* [Damping, Recorders, and Outputs](damping-recorders-and-outputs.md): Track the structural response under applied patterns.
* [Process and Analysis](process-and-analysis.md): Learn how solver steps execute load patterns.
