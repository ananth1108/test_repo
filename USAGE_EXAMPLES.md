# Usage Examples & Test Commands

## Quick Start

### Installation
```bash
cd /workspaces/test_repo
pip install -r requirements.txt
```

### Prepare Data
Place images in: `DATA/SAMPLE_SCENE/` or `DATA/YOUR_SCENE/`

Supported formats: `*.jpg`, `*.png`, `*.jpeg`

## Test Commands

### 1. Show Help
```bash
python sample.py --help
```

**Output**:
```
usage: sample.py [-h] [--scene SCENE] [--n_images N_IMAGES] [--conf CONF] [--device_test] [--preview]

DA3 3D Reconstruction Pipeline with Testing Modes

optional arguments:
  -h, --help            show this help message and exit
  --scene SCENE         Scene folder name (default: SAMPLE_SCENE)
  --n_images N_IMAGES   Max number of images to process (default: 5)
  --conf CONF           Confidence threshold for point filtering (default: 0.4)
  --device_test         Device test mode: check device, load model, verify images
  --preview             Preview mode: run inference on 1 image, show depth + PC
```

---

## Mode 1: Device Test

### Command
```bash
python sample.py --device_test
```

### What It Does
1. Checks available device (CUDA/CPU)
2. Loads Depth-Anything-3 model
3. Scans for images in `DATA/SAMPLE_SCENE/`
4. Lists found images
5. Exits

### Expected Output
```
============================================================
3D RECONSTRUCTION PIPELINE
============================================================
[INFO] Script location: /workspaces/test_repo
[INFO] Current working directory: /workspaces/test_repo
[INFO] Scene: SAMPLE_SCENE
[INFO] N images: 5
[INFO] Confidence threshold: 0.4
[INFO] Data path: /workspaces/test_repo/../../DATA/SAMPLE_SCENE
[INFO] Results path: /workspaces/test_repo/../../RESULTS/SAMPLE_SCENE

============================================================
DEVICE TEST MODE
============================================================
[CHECK] Device available: cuda
[CHECK] Loading DA3 model...
Using device: cuda
[SUCCESS] Model loaded successfully
[CHECK] Scanning for images in /workspaces/test_repo/../../DATA/SAMPLE_SCENE
Found 5 images in /workspaces/test_repo/../../DATA/SAMPLE_SCENE
[SUCCESS] Found 5 images
  - test_image_000.jpg
  - test_image_001.jpg
  - test_image_002.jpg
  - test_image_003.jpg
  - test_image_004.jpg

[DEVICE TEST COMPLETE] All checks passed!
```

### Use Case
- Verify CUDA availability
- Check if model can be loaded
- Ensure data folder structure is correct

---

## Mode 2: Preview Mode

### Command
```bash
python sample.py --preview
```

### What It Does
1. Loads **first image only**
2. Runs DA3 inference
3. Shows:
   - Depth map (matplotlib window)
   - Confidence map (matplotlib window)
   - Single-frame point cloud (Open3D window)
4. Exits

### Expected Output
```
============================================================
PREVIEW MODE
============================================================
[LOAD] Images from /workspaces/test_repo/../../DATA/SAMPLE_SCENE
Found 5 images in /workspaces/test_repo/../../DATA/SAMPLE_SCENE
[INFERENCE] Running DA3 on 1 image(s)...
[LOAD] Loading DA3 model...
Using device: cuda
[SUCCESS] Model loaded
[INFER] Processing image...
Depth maps shape: (1, 480, 640)
Extrinsics shape: (1, 4, 4)
Intrinsics shape: (1, 3, 3)
Confidence shape: (1, 480, 640)
[SUCCESS] Inference complete
[VIZ] Displaying depth + confidence...
[PC] Generating point cloud from frame 0...
[SUCCESS] Generated 307200 points
[VIZ] Displaying single-frame point cloud...

[PREVIEW COMPLETE]
```

### Variants
```bash
# Preview with custom confidence threshold
python sample.py --preview --conf 0.5

# Preview with different scene
python sample.py --preview --scene MY_SCENE

# (--n_images is ignored in preview mode, always processes 1)
```

### Use Case
- Quick inference test
- Verify depth estimation quality
- Check point cloud generation
- Fast feedback loop

---

## Mode 3: Full Pipeline

### Command
```bash
python sample.py --n_images 5
```

### What It Does (Complete Pipeline)
1. Load first 5 images
2. Run inference
3. Merge point clouds
4. Visualize merged cloud
5. Clean outliers (SOR)
6. Interactive ROI selection (optional - press Q to skip)
7. Multi-frame ICP registration
8. Ground plane segmentation
9. Object clustering
10. Label refinement
11. Voxelization
12. Visualization of all stages
13. Export PLY, GLB, voxel meshes

### Expected Output (partial)
```
============================================================
DEFAULT MODE: Full Pipeline
============================================================
[LOAD] Images from /workspaces/test_repo/../../DATA/SAMPLE_SCENE
Found 5 images in /workspaces/test_repo/../../DATA/SAMPLE_SCENE
[SELECT] Using first 5 images
[LOAD] Loading DA3 model...
Using device: cuda
[SUCCESS] Model loaded
[INFER] Running DA3 inference on 5 images...
...
[MERGE] Merging point clouds (conf_thresh=0.4)...
Merged point cloud: 1229476 points
[SUCCESS] Merged shape: (1229476, 3)
[VIZ] Displaying merged point cloud...
[CLEAN] Statistical outlier removal...
[SUCCESS] Cleaned shape: (1100234, 3) in 2.45s
...
[GROUND] Segmenting ground plane...
[SUCCESS] Ground segmentation complete in 0.32s
[STATS] Ground points: 450123 / 1100234 (40.9%)
...
[CLUSTER] DBSCAN clustering...
[SUCCESS] Clustering complete in 1.23s
[STATS] Clusters: 12, Noise points: 5432
...
[EXPORT] Exporting Gaussian Splatting PLY...
[SUCCESS] GS PLY exported to /workspaces/test_repo/../../RESULTS/SAMPLE_SCENE/gs_ply/
[EXPORT] Exporting GLB scene...
[SUCCESS] GLB scene exported: /workspaces/test_repo/../../RESULTS/SAMPLE_SCENE/glb/...
[EXPORT] Saving reconstruction PLY...
[SUCCESS] Saved 1100234 points to /workspaces/test_repo/../../RESULTS/SAMPLE_SCENE/reconstruction.ply
[EXPORT] Saving voxel meshes...
[SUCCESS] Voxel mesh (RGB) saved to /workspaces/test_repo/../../RESULTS/SAMPLE_SCENE/voxel_mesh_rgb.ply
[SUCCESS] Voxel mesh (seg) saved to /workspaces/test_repo/../../RESULTS/SAMPLE_SCENE/voxel_mesh_seg.ply

[PIPELINE COMPLETE]
```

### Variants
```bash
# Full pipeline with all 10 images
python sample.py --n_images 10

# Full pipeline with custom confidence
python sample.py --n_images 5 --conf 0.6

# Different scene
python sample.py --scene OFFICE --n_images 8

# Combine all custom parameters
python sample.py --scene WAREHOUSE --n_images 20 --conf 0.3
```

### Output Files
Generated in `RESULTS/SAMPLE_SCENE/`:
```
RESULTS/
└── SAMPLE_SCENE/
    ├── reconstruction.ply              # Point cloud with segmentation labels
    ├── voxel_mesh_rgb.ply             # RGB voxel mesh
    ├── voxel_mesh_seg.ply             # Segmentation label voxel mesh
    ├── gs_ply/                        # Gaussian splatting exports
    │   ├── gs.ply
    │   └── ...
    ├── glb/                           # GLB scene files
    │   ├── scene.glb
    │   └── ...
    └── masks/                         # Generated mask directory
```

### Use Case
- Complete 3D reconstruction
- Generate all output formats
- Full scene understanding
- Object segmentation and voxelization

---

## Advanced Usage

### Different Scene, Many Images
```bash
python sample.py --scene OFFICE --n_images 50 --conf 0.45
```

### Batch Processing Multiple Scenes
```bash
#!/bin/bash
for scene in OFFICE WAREHOUSE WAREHOUSE2; do
    echo "Processing $scene..."
    python sample.py --scene "$scene" --n_images 10
done
```

### Custom Confidence Experiments
```bash
# Low confidence (more points, less clean)
python sample.py --n_images 5 --conf 0.2

# Medium confidence (default)
python sample.py --n_images 5 --conf 0.4

# High confidence (fewer points, very clean)
python sample.py --n_images 5 --conf 0.7
```

---

## Error Scenarios & Solutions

### ERROR: No images found
**Cause**: Images in wrong location or filename
**Solution**:
```bash
# Check images exist
ls -la DATA/SAMPLE_SCENE/

# Verify file extensions (must be .jpg, .png, or .jpeg)
# Move images to correct location
```

### ERROR: FileNotFoundError: Data path does not exist
**Cause**: DATA folder doesn't exist relative to script
**Solution**:
```bash
# Check workspace structure
cd /workspaces/test_repo
python sample.py --device_test  # Will show expected path
mkdir -p DATA/SAMPLE_SCENE
# Add images there
```

### ERROR: ModuleNotFoundError: depth_anything_3
**Cause**: Dependencies not installed
**Solution**:
```bash
pip install -r requirements.txt
# Or specific dependencies:
pip install torch torchvision
pip install open3d numpy scipy
```

### WARNING: All points classified as noise!
**Cause**: DBSCAN clustering parameters too strict
**Solution**: Script continues with cluster_labels
```bash
# Adjust by re-running with different scene or check image quality
```

### Frame has too few registration points
**Cause**: Low confidence threshold or poor depth quality
**Solution**: Script skips ICP for that frame (continues with identity transform)
```bash
# Can increase confidence to get more points
python sample.py --conf 0.5
```

---

## Performance Tips

### For Fast Testing
```bash
# Use device test for quick pipeline check
python sample.py --device_test

# Use preview for single-image feedback
python sample.py --preview
```

### For High Quality
```bash
# More images, higher confidence
python sample.py --n_images 50 --conf 0.6
```

### For Memory Constraints
```bash
# Process fewer images at once
python sample.py --n_images 3
```

---

## Output Interpretation

### Looking at Results
```bash
# View results directory
ls -lah RESULTS/SAMPLE_SCENE/

# Visualize PLY in any viewer
# - Open3D viewer
# - CloudCompare
# - Meshlab
# - etc.
```

### File Sizes
- `reconstruction.ply`: ~10-100 MB (depends on point count)
- `voxel_mesh_rgb.ply`: ~1-10 MB (depends on voxel count)
- `gs_ply/gs.ply`: ~50-500 MB (Gaussian splatting)
- `glb/scene.glb`: ~10-100 MB (3D scene)

---
