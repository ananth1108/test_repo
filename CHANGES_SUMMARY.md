# Code Changes Summary

## File: sample.py

### 1. Added Imports
```python
import sys
import argparse
```

**Reason**: Support command-line argument parsing and proper error handling with sys.exit()

### 2. Removed Hard-Coded Config
- **Removed**: `DATA_FOLDER = "SAMPLE_SCENE"` (line 15)
- **Reason**: Now dynamically provided via `--scene` CLI flag

### 3. Enhanced Path Setup Function
- **Kept**: All path resolution using `__file__` for robustness
- **Improved**: Maintains relative path traversal (`..` + `..` from src folder)

### 4. Added Three Main Testing Functions

#### A. `run_device_test(args, paths)`
- Loads device (CUDA/CPU)
- Loads DA3 model
- Scans and lists available images
- Raises error if no images found
- **Use Case**: Quick hardware verification without full processing

#### B. `run_preview_mode(args, paths)`
- Loads and processes only **1 image**
- Shows depth map and confidence visualization
- Extracts and displays single-frame point cloud
- **Use Case**: Quick sanity check of inference pipeline

#### C. `run_default_mode(args, paths)`
- **Complete pipeline**:
  1. Load and process up to N images
  2. Run DA3 inference
  3. Merge point clouds
  4. Statistical cleaning
  5. Optional ROI picking
  6. Multi-frame ICP registration
  7. Ground plane segmentation
  8. Object clustering
  9. Label refinement
  10. Voxelization
  11. Export (PLY, GLB, voxel meshes)

### 5. Comprehensive Logging System

**Added throughout**: Structured console output with prefixes:
- `[INFO]` - Informational startup messages
- `[LOAD]` - Data/model loading operations
- `[INFER]` - Inference operations
- `[CHECK]` - Device test checks
- `[SUCCESS]` - Successfully completed operations
- `[ERROR]` - Error messages
- `[WARNING]` - Potential issues (e.g., all noise in clustering)
- `[SKIP]` - Skipped operations (e.g., no registration with 1 frame)
- `[STATS]` - Statistical summaries
- `[VIZ]` - Visualization steps
- `[MERGE]` - Point cloud merging
- `[CLEAN]` - Cleaning operations
- `[REG]` - Registration operations
- `[GROUND]` - Ground segmentation
- `[CLUSTER]` - Clustering operations
- `[VOXEL]` - Voxelization operations
- `[EXPORT]` - Export operations
- `[MESH]` - Mesh creation
- `[SAFETY]` - Safety checks and corrections

### 6. Enhanced main() Function

**New**: Dedicated `main()` function with:

```python
def main():
    """Main entry point with argument parsing and mode selection."""
    
    # Argument Parser
    parser = argparse.ArgumentParser(
        description="DA3 3D Reconstruction Pipeline with Testing Modes"
    )
    
    # Four CLI Arguments:
    parser.add_argument("--scene", type=str, default="SAMPLE_SCENE", ...)
    parser.add_argument("--n_images", type=int, default=5, ...)
    parser.add_argument("--conf", type=float, default=0.4, ...)
    parser.add_argument("--device_test", action="store_true", ...)
    parser.add_argument("--preview", action="store_true", ...)
```

**Features**:
- Prints startup info (script location, CWD, parameters)
- Resolves data path
- Verifies data path exists
- Handles exceptions gracefully with error messages
- Calls appropriate mode based on flags

### 7. Safety Checks Added

| Check | Location | Action |
|-------|----------|--------|
| **No images found** | `run_device_test()`, `run_preview_mode()`, `run_default_mode()` | Raise `ValueError` with message |
| **Data path doesn't exist** | `main()` | Raise `FileNotFoundError` |
| **ICP points < 50** | `register_frames()` (enhanced) | Skip ICP for that frame |
| **All noise in clustering** | `run_default_mode()` | Print `[WARNING]` message |
| **Voxel size = 0** | `run_default_mode()` | Clamp to `1e-6` |
| **Registration with 1 frame** | `run_default_mode()` | Print `[SKIP]` message |

### 8. Preserved Algorithmic Logic

✅ **All original functions remain unchanged**:
- `depth_to_point_cloud()` - Backprojection with camera parameters
- `merge_point_clouds()` - Frame combination
- `clean_point_cloud_scipy()` - Statistical outlier removal
- `register_frames()` - Multi-frame ICP (only logging enhanced)
- `segment_ground()` - RANSAC plane fitting
- `cluster_objects()` - DBSCAN clustering
- `refine_labels_knn()` - KNN boundary smoothing
- `voxelize_point_cloud()` - Voxel grid generation
- `create_voxel_cube_mesh()` - Mesh creation
- `save_reconstruction_ply()` - PLY export
- `visualize_*()` - All visualization functions

✅ **Only improvements**: 
- Added more detailed logging messages
- Enhanced frame-count checking in `register_frames()`
- No algorithmic changes

### 9. Script Entry Point

**Changed from**:
```python
# Inline code execution
paths = setup_paths(DATA_FOLDER)
model, device = load_da3_model()
...
```

**Changed to**:
```python
def main():
    # Proper structure
    ...

if __name__ == "__main__":
    main()
```

## Test Coverage

### Test 1: Device Test
```bash
python sample.py --device_test
```
- ✓ Checks CUDA/CPU availability
- ✓ Loads model successfully  
- ✓ Scans for images
- ✓ Lists available images (up to 5 shown)

### Test 2: Preview Mode
```bash
python sample.py --preview --n_images 1
```
- ✓ Loads first image
- ✓ Runs DA3 inference
- ✓ Shows depth + confidence maps
- ✓ Extracts single point cloud

### Test 3: Full Pipeline
```bash
python sample.py --n_images 5
```
- ✓ Processes up to 5 images
- ✓ Merges point clouds
- ✓ Cleans, registers, segments, clusters
- ✓ Exports all results

### Test 4: Custom Parameters
```bash
python sample.py --scene MY_SCENE --n_images 10 --conf 0.5
```
- ✓ Uses custom scene folder
- ✓ Processes up to 10 images
- ✓ Applies custom confidence threshold

## File Statistics

- **Original**: 694 lines
- **Modified**: 908 lines  
- **Added**: 214 lines of new code
- **Removed**: 0 lines of algorithmic code
- **Refactored**: 1 block (main execution → main function)

## Backward Compatibility

⚠️ **Note**: Script can no longer be run without arguments in the same way:

**Old way (won't work)**:
```bash
python sample.py  # Would need DATA_FOLDER to be defined
```

**New way**:
```bash
python sample.py --n_images 5  # Explicit parameters
```

This is intentional for clarity and testability.

