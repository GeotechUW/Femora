# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

import os

import numpy as np
from numpy import abs, arange, array, concatenate, isin, unique, where, zeros

from femora.components.element.ghost_node import GhostNodeElement
from femora.core.event_bus import FemoraEvent
from femora.utils.progress import Progress


def _progress_callback(value: float, message: str):
    """Default progress reporter that uses the shared Progress utility."""
    Progress.callback(value, message, desc="Exporting to TCL")


def _get_tcl_helper_functions():
    """
    Return TCL helper functions as a string.

    This method contains all the TCL helper functions needed for the exported model.
    Embedding them directly in the code ensures they're always available and makes
    the package more professional and self-contained.

    Returns:
        str: TCL helper functions
    """
    return '''proc getFemoraMax {type} {
	set local_max -1.e8
	if {$type == "eleTag"} {
		set Tags [getEleTags]
	} elseif {$type == "nodeTag"} {
		set Tags [getNodeTags]
	} else {
		puts "Unknown type $type"
		return -1
	}
	# set Tags [getNodeTags]
	foreach tag $Tags {
		if {$tag > $local_max} {
			set local_max $tag
		}
	}
	# send the max ele tag form each pid to the master
	if {$::pid == 0} {
		for {set i 1 } {$i < $::np} {incr i 1} { 
			recv -pid $i ANY maxTag
			if {$maxTag > $local_max} {
				set local_max $maxTag
			}
		}
	} else {
		send -pid 0 "$local_max"
	}

	# now send the max ele tag to all pids
	if {$::pid == 0} {
		for {set i 1 } {$i < $::np} {incr i 1} { 
			send -pid $i $local_max
		}
		set global_max $local_max
	} else {
		recv -pid 0 ANY global_max
	}
	return $global_max
}

'''


def _get_tcl_file_header(required_np: int) -> str:
    header = f"""
#   ╔══════════════════════════════════════════════════════════╗
#   ║                                                          ║
#   ║   ███████╗███████╗███╗   ███╗ ██████╗ ██████╗  █████╗    ║
#   ║   ██╔════╝██╔════╝████╗ ████║██╔═══██╗██╔══██╗██╔══██╗   ║
#   ║   █████╗  █████╗  ██╔████╔██║██║   ██║██████╔╝███████║   ║
#   ║   ██╔══╝  ██╔══╝  ██║╚██╔╝██║██║   ██║██╔══██╗██╔══██║   ║
#   ║   ██║     ███████╗██║ ╚═╝ ██║╚██████╔╝██║  ██║██║  ██║   ║
#   ║   ╚═╝     ╚══════╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝   ║
#   ║══════════════════════════════════════════════════════════║
#   ║            Soil-Structure Interaction Analysis           ║
#   ║             Femora Tcl Export                            ║
#   ║             Developers: Amin Pakzad, Pedro Arduino       ║
#   ║             License: MIT                                 ║
#   ║             Required MPI processes: {required_np:<17}    ║
#   ║══════════════════════════════════════════════════════════║
#   ╚══════════════════════════════════════════════════════════╝
"""
    return header


def export_to_tcl(model, filename=None, progress_callback=None, decimals=5):
    """
    Export the model to a TCL file

    Args:
        model: Femora Model instance with an assembled mesh.
        filename (str, optional): The filename to export to. If None,
                                 uses model_name in model_path
        progress_callback (callable, optional): Callback function to report progress.
                                              If None, uses tqdm progress bar.

    Returns:
        bool: True if export was successful, False otherwise

    Raises:
        ValueError: If no filename is provided and model_name/model_path are not set
    """
    # Use the default tqdm progress callback if none is provided
    if progress_callback is None:
        progress_callback = _progress_callback

    if True:
        # Determine the full file path
        if filename is None:
            if model.model_name is None or model.model_path is None:
                raise ValueError("Either provide a filename or set model_name and model_path")
            filename = os.path.join(model.model_path, f"{model.model_name}.tcl")

        # chek if the end is not .tcl then add it
        if not filename.endswith('.tcl'):
            filename += '.tcl'
        # Ensure the directory exists
        os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)

        # Get the assembled content
        if model.assembled_mesh is None:
            print("No mesh found")
            raise ValueError("No mesh found\n Please assemble the mesh first")

        # Write to file
        with open(filename, 'w', encoding='utf-8') as f:

            # Determine required MPI process count for this model export
            required_np = 1
            try:
                core_ids = np.asarray(model.assembled_mesh.cell_data["Core"])
                if core_ids.size:
                    required_np = int(np.max(np.unique(core_ids))) + 1
            except Exception:
                required_np = 1

            # Write a banner/header at the very beginning of the file
            f.write(_get_tcl_file_header(required_np))

            # Inform interfaces that we are about to export
            model.events.emit(FemoraEvent.PRE_EXPORT, file_handle=f, assembled_mesh=model.assembled_mesh)

            f.write("wipe\n")
            f.write("set pid [getPID]\n")
            f.write("set np [getNP]\n")

            # Validate MPI process count early
            f.write(f"set FEMORA_REQUIRED_NP {required_np}\n")
            f.write("if {$np != $FEMORA_REQUIRED_NP} {\n")
            f.write("\tif {$pid == 0} {\n")
            f.write("\t\tputs \"ERROR: This model requires $FEMORA_REQUIRED_NP MPI processes, but OpenSees is running with $np.\"\n")
            f.write("\t\tputs \"Please re-run with: mpiexec/mpirun -np $FEMORA_REQUIRED_NP OpenSeesMP <script.tcl>\"\n")
            f.write("\t}\n")
            f.write("\texit 2\n")
            f.write("}\n")
            f.write("model BasicBuilder -ndm 3\n")

            if model._results_folder != "":
                f.write("if {$pid == 0} {" + f"file mkdir {model._results_folder}" + "} \n")

            f.write("\n# Helper functions ======================================\n")
            f.write(_get_tcl_helper_functions())

            # Write the meshBounds
            f.write("\n# Mesh Bounds ======================================\n")
            bounds = model.assembled_mesh.bounds
            f.write(f"set X_MIN {bounds[0]}\n")
            f.write(f"set X_MAX {bounds[1]}\n")
            f.write(f"set Y_MIN {bounds[2]}\n")
            f.write(f"set Y_MAX {bounds[3]}\n")
            f.write(f"set Z_MIN {bounds[4]}\n")
            f.write(f"set Z_MAX {bounds[5]}\n")

            if progress_callback:
                progress_callback(0, "writing materials")


            # Write the materials
            f.write("\n# Materials ======================================\n")
            for tag, mat in model.material.get_all().items():
                f.write(f"{mat.to_tcl()}\n")

            # write the transformations
            f.write("\n# Transformations ======================================\n")
            for transf in model.transformation:
                f.write(f"{transf.to_tcl()}\n")

            # Write the sections
            f.write("\n# Sections ======================================\n")
            for tag, section in model.section.get_all().items():
                f.write(f"{section.to_tcl()}\n")

            if progress_callback:
                progress_callback(5,"writing nodes and elements")

            # Write the nodes
            f.write("\n# Nodes & Elements ======================================\n")
            cores = model.assembled_mesh.cell_data["Core"]
            num_cores = unique(cores)
            nodes     = model.assembled_mesh.points
            ndfs      = model.assembled_mesh.point_data["ndf"]
            mass      = model.assembled_mesh.point_data["Mass"]
            num_nodes = model.assembled_mesh.n_points
            wroted    = zeros((num_nodes, len(num_cores)), dtype=bool) # to keep track of the nodes that have been written
            core_to_idx = {int(core): idx for idx, core in enumerate(num_cores)}
            node_owner = np.full(num_nodes, -1, dtype=int)
            nodeTags  = arange(model._start_nodetag,
                               model._start_nodetag + num_nodes,
                               dtype=int)
            eleTags   = arange(model._start_ele_tag,
                               model._start_ele_tag + model.assembled_mesh.n_cells,
                               dtype=int)


            elementClassTag = model.assembled_mesh.cell_data["ElementTag"]


            for i in range(model.assembled_mesh.n_cells):
                cell = model.assembled_mesh.get_cell(i)
                pids = cell.point_ids
                core = cores[i]
                f.write("if {$pid ==" + str(core) + "} {\n")
                # writing nodes
                for pid in pids:
                    core_idx = core_to_idx[int(core)]
                    if not wroted[pid][core_idx]:
                        # Resolve potential ghost node sentinels back to real DOFs
                        raw_ndf = ndfs[pid]
                        real_ndf = GhostNodeElement.resolve_ndf(raw_ndf) if raw_ndf >= 1000 else raw_ndf
                        f.write(f"\tnode {nodeTags[pid]} {round(nodes[pid][0], decimals)} {round(nodes[pid][1], decimals)} {round(nodes[pid][2], decimals)} -ndf {real_ndf}\n")
                        if node_owner[pid] < 0:
                            node_owner[pid] = int(core)
                        wroted[pid][core_idx] = True

                eleclass = model.element.get(elementClassTag[i])
                nodeTag = [nodeTags[pid] for pid in pids]
                eleTag = eleTags[i]
                f.write("\t"+eleclass.to_tcl(eleTag, nodeTag) + "\n")
                f.write("}\n")
                if progress_callback:
                    progress_callback((i / model.assembled_mesh.n_cells) * 45 + 5, "writing nodes and elements")

            # Emit each assembled node mass once, on the node's owner PID.
            # The node itself is still declared on every PID that uses it.
            f.write("\n# Nodal masses ======================================\n")
            for core in num_cores:
                owned_nodes = where(node_owner == int(core))[0]
                if owned_nodes.size == 0:
                    continue
                f.write("if {$pid ==" + str(core) + "} {\n")
                for node_idx in owned_nodes:
                    raw_ndf = ndfs[node_idx]
                    real_ndf = GhostNodeElement.resolve_ndf(raw_ndf) if raw_ndf >= 1000 else raw_ndf
                    mass_vec = mass[node_idx][:real_ndf]
                    if abs(mass_vec).sum() > 1e-6:
                        f.write(f"\tmass {nodeTags[node_idx]} {' '.join(map(str, mass_vec))}\n")
                f.write("}\n")

            # notify EmbbededBeamSolidInterface event
            model.events.emit(FemoraEvent.INTERFACE_ELEMENTS_TCL, file_handle=f)
            model.events.emit(FemoraEvent.EMBEDDED_BEAM_SOLID_TCL, file_handle=f)


            if progress_callback:
                progress_callback(50, "writing dampings")
            # writ the dampings
            f.write("\n# Dampings ======================================\n")
            if model.damping.get_all() is not None:
                for tag,damp in model.damping.get_all().items():
                    f.write(f"{damp.to_tcl()}\n")
            else:
                f.write("# No dampings found\n")

            if progress_callback:
                progress_callback(55, "writing regions")

            # write regions
            f.write("\n# Regions ======================================\n")
            Regions = unique(model.assembled_mesh.cell_data["Region"])
            for i,regionTag in enumerate(Regions):
                region = model.region.get(regionTag)
                if region.get_type().lower() == "noderegion":
                    raise ValueError(f"""Region {regionTag} is of type NodeTRegion which is not supported in yet""")

                region.elements = list(eleTags[model.assembled_mesh.cell_data["Region"] == regionTag])
                region.element_range = []
                f.write(f"{region.to_tcl()} \n")
                del region
                if progress_callback:
                    progress_callback((i / Regions.shape[0]) * 10 + 55, "writing regions")

            element_groups = []
            if hasattr(model, "group"):
                element_groups = list(model.group.element.get_all().values())
            if element_groups:
                f.write("\n# Element Groups ======================================\n")
                region_tags = [int(tag) for tag in model.region.get_all().keys()]
                next_group_tag = max(region_tags + [int(tag) for tag in Regions] + [0]) + 1
                for group in element_groups:
                    group.assign_tag(next_group_tag)
                    next_group_tag += 1
                    f.write(f"{group.to_tcl(eleTags)} \n")

            if progress_callback:
                progress_callback(65, "writing constraints")


            # Write mp constraints
            f.write("\n# mpConstraints ======================================\n")

            # Precompute mappings
            core_to_idx = {core: idx for idx, core in enumerate(num_cores)}
            master_nodes = zeros(num_nodes, dtype=bool)
            slave_nodes = zeros(num_nodes, dtype=bool)

            # Modified data structures to handle multiple constraints per node
            constraint_map = {}  # map master node to list of constraints
            constraint_map_rev = {}  # map slave node to list of (master_id, constraint) tuples

            for constraint in model.constraint.mp:
                master_id = constraint.master_node - 1
                master_nodes[master_id] = True

                # Add constraint to master's list
                if master_id not in constraint_map:
                    constraint_map[master_id] = []
                constraint_map[master_id].append(constraint)

                # For each slave, record the master and constraint
                for slave_id in constraint.slave_nodes:
                    slave_id = slave_id - 1
                    slave_nodes[slave_id] = True

                    if slave_id not in constraint_map_rev:
                        constraint_map_rev[slave_id] = []
                    constraint_map_rev[slave_id].append((master_id, constraint))

            # Get mesh data
            cells = model.assembled_mesh.cell_connectivity
            offsets = model.assembled_mesh.offset

            for core_idx, core in enumerate(num_cores):
                # Get elements in current core
                eleids = where(cores == core)[0]
                if eleids.size == 0:
                    continue

                # Get all nodes in this core's elements
                starts = offsets[eleids]
                ends = offsets[eleids + 1]
                core_node_indices = concatenate([cells[s:e] for s, e in zip(starts, ends)])
                in_core = isin(arange(num_nodes), core_node_indices)
                
                # Find active masters and slaves in this core
                active_masters = where(master_nodes & in_core)[0]
                active_slaves = where(slave_nodes & in_core)[0]

                # Add the master nodes that are not in the core but needed for constraints
                masters_to_add = []
                for slave_id in active_slaves:
                    if slave_id in constraint_map_rev:
                        for master_id, _ in constraint_map_rev[slave_id]:
                            masters_to_add.append(master_id)

                # Add unique masters
                if masters_to_add:
                    active_masters = concatenate([active_masters, array(masters_to_add)])
                    active_masters = unique(active_masters)

                if not active_masters.size:
                    continue

                f.write(f"if {{$pid == {core}}} {{\n")

                # Process all master nodes that are not in the current core
                valid_mask = ~in_core[active_masters]
                valid_masters = active_masters[valid_mask]
                if valid_masters.size > 0:
                    f.write("\t# Master nodes not defined in this core\n")
                    for master_id in valid_masters:
                        node = nodes[master_id]
                        raw_ndf = ndfs[master_id]
                        real_ndf = GhostNodeElement.resolve_ndf(raw_ndf) if raw_ndf >= 1000 else raw_ndf
                        f.write(f"\tnode {nodeTags[master_id]} {round(node[0], decimals)} {round(node[1], decimals)} {round(node[2], decimals)} -ndf {real_ndf}\n")


                # Process all slave nodes that are not in the current core
                # Collect all unique slave nodes from active master nodes' constraints
                all_slaves = []
                for master_id in active_masters:
                    for constraint in constraint_map[master_id]:
                        all_slaves.extend([sid - 1 for sid in constraint.slave_nodes])

                # Filter out slave nodes that are not in the current core
                valid_slaves = array([sid for sid in all_slaves if 0 <= sid < num_nodes and not in_core[sid]])

                if valid_slaves.size > 0:
                    f.write("\t# Slave nodes not defined in this core\n")
                    for slave_id in unique(valid_slaves):
                        node = nodes[slave_id]
                        raw_ndf = ndfs[slave_id]
                        real_ndf = GhostNodeElement.resolve_ndf(raw_ndf) if raw_ndf >= 1000 else raw_ndf
                        f.write(f"\tnode {nodeTags[slave_id]} {round(node[0], decimals)} {round(node[1], decimals)} {round(node[2], decimals)} -ndf {real_ndf}\n")

                # Write constraints after nodes
                f.write("\t# Constraints\n")

                # Process constraints where master is in this core
                for master_id in active_masters:
                    for constraint in constraint_map[master_id]:
                        f.write(f"\t{constraint.to_tcl()}\n")

                f.write("}\n")

                if progress_callback:
                    progress = 65 + (core_idx + 1) / len(num_cores) * 15
                    progress_callback(min(progress, 80), "writing constraints")

            # write sp constraints
            f.write("\n# spConstraints ======================================\n")
            size = len(model.constraint.sp)
            indx = 1
            for constraint in model.constraint.sp:
                f.write(f"{constraint.to_tcl()}\n")
                if progress_callback:
                    progress_callback(80 + indx / size * 5, "writing sp constraints")
                indx += 1


            # write time series
            f.write("\n# Time Series ======================================\n")
            size = len(model.time_series)
            indx = 1
            for timeSeries in model.time_series:
                f.write(f"{timeSeries.to_tcl()}\n")
                if progress_callback:
                    progress_callback(85 + indx / size * 5, "writing time series")
                indx += 1

            # write process
            f.write("\n# Process ======================================\n")
            indx = 1
            size = len(model.process)
            f.write(f"{model.process.to_tcl()}\n")

            f.write("exit\n")
            # for process in model.process:
            #     print(process["component"])
            #     f.write(f"{process['component'].to_tcl()}\n")
            #     if progress_callback:
            #         progress_callback(90 + indx / size * 10, "writing process")
            #     indx += 1




            if progress_callback:
                progress_callback(100,"finished writing")

    return True
