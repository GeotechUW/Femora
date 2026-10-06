# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

import sys
import os
import pytest

# Add src to path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, '..', 'src'))
sys.path.append(src_dir)

# Mock Material if needed, but ASDEmbeddedNodeElement3D doesn't use it
from femora.components.element import ASDEmbeddedNodeElement3D


def test_asd_embedded_node_rejects_contact_options():
    with pytest.raises(TypeError, match="use EmbeddedNodeContact instead"):
        ASDEmbeddedNodeElement3D(ndof=3, contact=True)

def test_asd_embedded_node_3d():
    print("Testing ASDEmbeddedNodeElement3D...")
    
    # 1. Create element with minimal params
    # ndof can be 3, 4, or 6
    ele1 = ASDEmbeddedNodeElement3D(ndof=3)
    tcl1 = ele1.to_tcl(tag=10, nodes=[1, 2, 3, 4, 5])
    print(f"Minimal TCL: {tcl1}")
    expected1 = "element ASDEmbeddedNodeElement 10 1 2 3 4 5"
    if tcl1 != expected1:
        print(f"Error: expected '{expected1}' (len {len(expected1)})")
        print(f"got      '{tcl1}' (len {len(tcl1)})")
        sys.exit(1)

    # 2. Create element with all params
    ele2 = ASDEmbeddedNodeElement3D(ndof=6, rot=True, p=True, K=2e20, KP=3e19)
    tcl2 = ele2.to_tcl(tag=20, nodes=[10, 11, 12, 13, 14])
    print(f"Full TCL: {tcl2}")
    
    if "-rot" not in tcl2:
        print("Error: -rot flag missing")
        sys.exit(1)
    if "-p" not in tcl2:
        print("Error: -p flag missing")
        sys.exit(1)
    if "-K 2e+20" not in tcl2 and "-K 2.0e+20" not in tcl2:
        print("Error: -K parameter missing or incorrect")
        sys.exit(1)
    if "-KP 3e+19" not in tcl2 and "-KP 3.0e+19" not in tcl2:
        print("Error: -KP parameter missing or incorrect")
        sys.exit(1)

    print("All tests passed!")

if __name__ == "__main__":
    test_asd_embedded_node_3d()
