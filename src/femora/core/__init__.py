"""---
icon: material/cog-outline
---

Build, organize, and export a model through model-owned services.

Start with [Model][femora.core.model.Model]. Its attributes provide managers
such as ``model.material``, ``model.meshpart``, and ``model.analysis``. These
managers create, register, and look up the objects belonging to that model.
You normally use these attributes rather than constructing managers yourself.

## From a definition to a solver script

For example, creating a material returns an object that an element definition
can reference. A mesh part combines a mesh with an element definition.
Assembly combines and partitions mesh parts. Finally, export writes the
assembled domain and ordered process to Tcl; it does not launch OpenSees.

```python
from femora import Model

model = Model(model_name="frame_site", model_path="example_outputs/frame_site")
soil = model.material.nd.elastic_isotropic(
    user_name="soil", E=108000.0, nu=1.0 / 3.0, rho=1.8,
)
assert model.material.get(soil.tag) is soil
model.process.add_step(model.actions.set_time(0.0), "Initialize clock")
```

This short example defines a material and a process action, not a complete
solvable domain. Meshes, connectivity, supports, loading, and analysis settings
must be supplied for an actual analysis. Keep a consistent unit system.

## How to read this reference

Each subject groups its manager with the objects and namespaces it exposes.
Manager pages explain the normal entry point, parameters, and returned values.
The Components reference describes concrete material, element, and other
component types. Follow those links for type-specific modeling options.

An **extension API** contains base contracts for implementing new component
types. You do not need to subclass those bases for ordinary model construction.
The advanced section covers model lifecycle events rather than routine setup.
Expand individual members to read their details without opening every method.

## Choose a subject

- [Model](Model/): model ownership, output settings, clearing, and export.
- [Materials](MaterialManager/), [sections](SectionManager/),
  [transformations](TransformationManager/), and [elements](ElementManager/):
  physical and finite-element definitions.
- [Mesh parts](MeshPartManager/) and [assembly](Assembler/): construct and
  combine the discretized domain.
- [Interfaces](InterfaceManager/) and [constraints](ConstraintManager/):
  connect components and prescribe degrees of freedom.
- [Damping](DampingManager/), [mass](MassManager/), and [regions](RegionManager/):
  assign dynamic properties and organize parts of the domain.
- [Selections](GroupManager/) and [masks](MaskManager/): identify nodes and elements.
- [Time series](TimeSeriesManager/), [ground motions](GroundMotionManager/),
  [loads](LoadManager/), and [patterns](PatternManager/): define loading.
- [Recorders](RecorderManager/): define solver response output.
- [Actions](ActionManager/), [analysis](AnalysisManager/), and
  [process](ProcessManager/): configure and order solver operations.
- [Lifecycle events](ModelEventBus/): subscribe to model lifecycle notifications.

For running exported scripts, see the runtime API. For orchestrating multiple
builds and solver invocations, see Jobs. Those execution layers are separate
from a model's ordered process.
"""

from .element_base import Element
from .element_manager import ElementManager
from .ground_motion_base import GroundMotion
from .ground_motion_manager import GroundMotionManager
from .tagging import CompactRetagPolicy, TaggingPolicy, TaggedObject
from femora.components.ground_motion import PlainGroundMotion, InterpolatedGroundMotion
