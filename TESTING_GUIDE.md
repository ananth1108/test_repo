# Modified Script: Testing Guide & Usage

## Summary of Changes

The `sample.py` script has been enhanced with proper CLI structure, three testing modes, comprehensive logging, and safety checks while preserving all algorithmic logic.

### Key Improvements

✅ **CLI Structure**
- Added `argparse` argument parser
- Proper `main()` function as entry point
- Four command-line flags:
  - `--scene` (default="SAMPLE_SCENE"): Scene folder name
  - `--n_images` (default=5): Max number of images to process
  - `--conf` (default=0.4): Confidence threshold for point filtering
  - `--device_test`: Device test mode (check device & model)
  - `--preview`: Preview mode (1 image inference)

✅ **Enhanced Path Handling**
- Uses `__file__` for robust relative path resolution
- Prints current working directory at startup
- Prints resolved data path with verification
- Creates all necessary output directories

✅ **Three Testing Modes**

| Mode | Command | Purpose |
|------|---------|---------|
| **Device Test** | `python sample.py --device_test` | Quick check: device, model load, image existence |
| **Preview** | `python sample.py --preview --n_images 1` | Single image inference with depth/confidence/PC visualization |
| **Default (Full)** | `python sample.py --n_images 5` | Complete pipeline with all processing stages |

✅ **Console Logging**
- `[INFO]` tags for informational messages
- `[LOAD]` for loading operations
- `[INFER]` for inference
- `[SUCCESS]` for completed operations
- `[ERROR]` for failures
- `[WARNING]` for potential issues
- `[STATS]` for statistical summaries
- `[VIZ]` for visualization steps

✅ **Safety Checks**
- ✓ If no images found → raises `ValueError` with clear message
- ✓ If ICP has < 50 points → skips registration with message
- ✓ If clustering returns all noise → prints warning
- ✓ If voxel size is zero → clamps to epsilon (1e-6)
- ✓ Data path existence verification before processing
- ✓ Registration skipped if only 1 frame is available

✅ **Major Processing Checkpoints**
At each major step, the script prints:
- Model loaded status
- Inference completion with shape info
- Merged point cloud shape
- Cleaned point cloud shape
- Registration success/skip status with detailed feedback
- Ground segmentation statistics (count, percentage)
- Clustering statistics (number of clusters, noise points)
- Voxelization statistics (number of voxels)
- Export file paths and completion status

## Example Commands

### 1. Device Test Mode
```bash
python sample.py --device_test
```
**Output**: ✓ Device available, ✓ Model loaded, ✓ Images found

### 2. Preview Mode (Single Image)
```bash
python sample.py --preview --n_images 1
```
**Output**: Shows depth map, confidence map, and extracted point cloud from first image

### 3. Default Mode (Full Pipeline)
```bash
python sample.py --n_images 5
```
**Output**: Runs complete pipeline on first 5 images with all visualizations

### 4. Custom Confidence Threshold
```bash
python sample.py --n_images 3 --conf 0.5
```
**Output**: Uses 0.5 confidence threshold instead of default 0.4

### 5. Different Scene
```bash
python sample.py --scene MY_SCENE --n_images 10
```
**Output**: Processes images from `DATA/MY_SCENE/` directory

### 6. Device Test with Custom Scene
```bash
python sample.py --device_test --scene MY_SCENE
```
**Output**: Verifies device and images for MY_SCENE

## Expected Console Output Example

```
============================================================
3D RECONSTRUCTION PIPELINE
============================================================
[INFO] Script location: /workspaces/test_repo/src
[INFO] Current working directory: /workspaces/test_repo
[INFO] Scene: SAMPLE_SCENE
[INFO] N images: 5
[INFO] Confidence threshold: 0.4
[INFO] Data path: /workspaces/test_repo/../../DATA/SAMPLE_SCENE
[INFO] Results path: /workspaces/test_repo/../../RESULTS/SAMPLE_SCENE

============================================================
DEFAULT MODE: Full Pipeline
============================================================
[LOAD] Images from /workspaces/test_repo/../../DATA/SAMPLE_SCENE
Found 5 images in /workspaces/test_repo/../../DATA/SAMPLE_SCENE
[SELECT] Using first 5 images
[LOAD] Loading DA3 model...
Using device: cuda
[SUCCESS] Model loaded
[INFER] Running DA3 inference on 5 image(s)...
Depth maps shape: (5, 480, 640)
[SUCCESS] Inference complete
[MERGE] Merging point clouds (conf_thresh=0.4)...
Merged point cloud: 2450000 points
[SUCCESS] Merged shape: (2450000, 3)
...
```

## Error Handling Examples

### No Images Found
```
ERROR: No images found in /workspaces/test_repo/../../DATA/SAMPLE_SCENE
```

### Invalid Data Path
```
FileNotFoundError: Data path does not exist: /path/to/DATA/SCENE
```

### ICP Frame Too Small
```
Frame 2: too few reg points (45 < 50); skipping ICP
```

### All Noise in Clustering
```
[WARNING] All points classified as noise! Check eps/min_points parameters.
```

### Voxel Size Safety Clamp
```
[SAFETY] Voxel size was 0; clamped to 1.00e-06
```

## Pipeline Execution Stages

The full pipeline executes in this order:

1. **Model Loading** → Load Depth-Anything-3
2. **Image Inference** → Run DA3 on selected images
3. **Point Cloud Merging** → Combine frames with confidence filtering
4. **Visualization** → Display merged cloud
5. **Statistical Cleaning** → Remove outliers (SOR)
6. **ROI Selection** (interactive) → Optional point picking
7. **Registration** → Multi-frame ICP alignment (if >1 frame)
8. **Post-Registration Cleaning** → Remove outliers again
9. **Ground Segmentation** → RANSAC plane fitting
10. **Object Clustering** → DBSCAN on non-ground points
11. **Label Refinement** → KNN boundary smoothing
12. **Voxelization** → Create structured voxel grid
13. **Export** → Save PLY, GLB, and voxel meshes

## Prerequisites

```bash
pip install -r requirements.txt
```

Required packages:
- torch, torchvision
- depth-anything-v3
- open3d
- numpy, scipy
- matplotlib
- xformers, gsplat

## Data Structure Expected

```
/workspaces/test_repo/
├── sample.py (modified script)
├── DATA/
│   └── SAMPLE_SCENE/
│       ├── image_001.jpg
│       ├── image_002.jpg
│       └── ... (*.jpg, *.png, *.jpeg)
└── RESULTS/
    └── SAMPLE_SCENE/
        ├── reconstruction.ply
        ├── voxel_mesh_rgb.ply
        ├── voxel_mesh_seg.ply
        ├── gs_ply/ (Gaussian splatting exports)
        └── glb/ (GLB scene files)
```

## Algorithmic Integrity

✅ **NO algorithmic changes** - All processing logic preserved:
- Depth-to-3D backprojection using camera parameters
- Camera pose composition (world/camera transformations)
- Point cloud merging with per-frame tracking
- Statistical outlier removal (SOR with cKDTree)
- Multi-frame ICP registration with robustness checks
- RANSAC ground plane segmentation
- DBSCAN object clustering
- Voxel grid construction with majority voting
- KNN-based label refinement

Only **structural improvements**: Testing modes, CLI interface, logging, and safety checks.

## Notes

- Interactive ROI picking (Shift+Click) in default mode can be skipped by pressing Q
- Visualizations use Open3D windows - close to continue
- All file paths are resolved relative to script location
- Timestamps are printed for each major operation
- With CUDA GPU: Inference typically <1s per image
- Voxel size auto-computed from point cloud extent (can override with `--voxel_size` if needed)

