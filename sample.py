import time
import glob
import os
import sys
import argparse
import torch
import numpy as np
import open3d as o3d
import matplotlib.pyplot as plt
from depth_anything_3.api import DepthAnything3

from scipy.spatial import cKDTree

# ----------------------------
# Config
# ----------------------------
EXTRINSICS_ARE_CAM2WORLD = True  # If your cloud looks wrong, set False

# ----------------------------
# Helpers: paths, viz
# ----------------------------
def setup_paths(data_folder="SAMPLE_SCENE"):
    """Create project paths for data, results, and masks."""
    base = os.path.dirname(os.path.abspath(__file__))  # folder of this .py file
    data_root = os.path.normpath(os.path.join(base, "..", "..", "DATA"))
    results_root = os.path.normpath(os.path.join(base, "..", "..", "RESULTS"))

    paths = {
        "data": os.path.join(data_root, data_folder),
        "results": os.path.join(results_root, data_folder),
        "masks": os.path.join(results_root, data_folder, "masks"),
    }
    os.makedirs(paths["results"], exist_ok=True)
    os.makedirs(paths["masks"], exist_ok=True)
    return paths

def visualize_depth_and_confidence(images, depths, confs, sample_idx=0, figsize=(12, 4)):
    """Quick matplotlib visualization for sanity-check."""
    img = images[sample_idx]
    d = depths[sample_idx]
    c = confs[sample_idx]

    plt.figure(figsize=figsize)

    plt.subplot(1, 3, 1)
    plt.title("RGB")
    plt.imshow(img)
    plt.axis("off")

    plt.subplot(1, 3, 2)
    plt.title("Depth")
    plt.imshow(d, cmap="inferno")
    plt.axis("off")

    plt.subplot(1, 3, 3)
    plt.title("Confidence")
    plt.imshow(c, cmap="viridis", vmin=0, vmax=1)
    plt.axis("off")

    plt.tight_layout()
    plt.show()

def visualize_point_cloud_open3d(points, colors=None, window_name="Point Cloud"):
    """Open3D point cloud visualizer."""
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
    if colors is not None:
        pcd.colors = o3d.utility.Vector3dVector(colors.astype(np.float64))
    o3d.visualization.draw_geometries([pcd], window_name=window_name)

# ----------------------------
# Model
# ----------------------------
def load_da3_model(model_name="depth-anything/DA3NESTED-GIANT-LARGE"):
    """Initialize Depth-Anything-3 model on available device."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    model = DepthAnything3.from_pretrained(model_name).to(device=device)
    return model, device

def load_images_from_folder(data_path, extensions=("*.jpg", "*.png", "*.jpeg")):
    """Scan folder and load all image file paths."""
    image_files = []
    for ext in extensions:
        image_files.extend(sorted(glob.glob(os.path.join(data_path, ext))))
    print(f"Found {len(image_files)} images in {data_path}")
    return image_files

def run_da3_inference(model, image_files, process_res_method="upper_bound_resize"):
    """Run DA3 to get depth maps, camera poses, and intrinsics."""
    prediction = model.inference(
        image=image_files,
        infer_gs=True,
        process_res_method=process_res_method,
    )
    print(f"Depth maps shape: {prediction.depth.shape}")
    print(f"Extrinsics shape: {prediction.extrinsics.shape}")
    print(f"Intrinsics shape: {prediction.intrinsics.shape}")
    print(f"Confidence shape: {prediction.conf.shape}")
    return prediction

# ----------------------------
# Geometry: depth -> points
# ----------------------------
def camera_to_world_points(pts_cam, extrinsics, cam2world=True):
    """
    Convert Nx3 camera points to world points.
    If cam2world=True: world = cam @ R.T + t
    If cam2world=False (world->cam extrinsics): invert the transform.
    """
    R = extrinsics[:3, :3]
    t = extrinsics[:3, 3]
    if cam2world:
        return (pts_cam @ R.T) + t
    else:
        # world->cam: x_cam = R x_world + t  => x_world = (x_cam - t) @ R
        return (pts_cam - t) @ R

def depth_to_point_cloud(depth_map, rgb_image, intrinsics, extrinsics, conf_map=None, conf_thresh=0.5):
    """Back-project depth map to 3D points using camera parameters."""
    h, w = depth_map.shape
    fx, fy = intrinsics[0, 0], intrinsics[1, 1]
    cx, cy = intrinsics[0, 2], intrinsics[1, 2]

    u, v = np.meshgrid(np.arange(w), np.arange(h))

    if conf_map is not None:
        valid = conf_map > conf_thresh
    else:
        valid = np.ones((h, w), dtype=bool)

    u = u[valid].astype(np.float32)
    v = v[valid].astype(np.float32)
    d = depth_map[valid].astype(np.float32)

    rgb = rgb_image[valid].reshape(-1, 3).astype(np.float32) / 255.0

    x = (u - cx) * d / fx
    y = (v - cy) * d / fy
    z = d
    pts_cam = np.stack([x, y, z], axis=-1)

    pts_world = camera_to_world_points(pts_cam, extrinsics, cam2world=EXTRINSICS_ARE_CAM2WORLD)
    return pts_world, rgb

def merge_point_clouds(prediction, conf_thresh=0.5):
    """Combine all frames into a single cloud, also return per-frame clouds."""
    all_points, all_colors = [], []
    n_frames = len(prediction.depth)

    for i in range(n_frames):
        pts, cols = depth_to_point_cloud(
            prediction.depth[i],
            prediction.processed_images[i],
            prediction.intrinsics[i],
            prediction.extrinsics[i],
            prediction.conf[i],
            conf_thresh,
        )
        all_points.append(pts)
        all_colors.append(cols)

    merged_points = np.vstack(all_points)
    merged_colors = np.vstack(all_colors)
    print(f"Merged point cloud: {len(merged_points)} points")
    return merged_points, merged_colors, all_points, all_colors

# ----------------------------
# Cleaning (SOR)
# ----------------------------
def clean_point_cloud_scipy(points_3d, colors_3d, nb_neighbors=20, std_ratio=2.0):
    """Statistical outlier removal using cKDTree."""
    tree = cKDTree(points_3d)
    distances, _ = tree.query(points_3d, k=nb_neighbors + 1, workers=-1)
    mean_dist = np.mean(distances[:, 1:], axis=1)
    thr = mean_dist.mean() + std_ratio * mean_dist.std()
    mask = mean_dist < thr
    return points_3d[mask], colors_3d[mask]

# ----------------------------
# ROI selection (robust)
# ----------------------------
def interactive_roi_from_picks(points, colors=None):
    """
    Pick points (Shift+LMB), press Q to finish.
    ROI is bbox of picked points.
    """
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    if colors is not None:
        pcd.colors = o3d.utility.Vector3dVector(colors)

    print("Pick ROI points: Shift+LeftClick to pick, then press Q to exit.")
    vis = o3d.visualization.VisualizerWithEditing()
    vis.create_window(window_name="Pick ROI points (Shift+Click), Q to finish")
    vis.add_geometry(pcd)
    vis.run()
    picked = vis.get_picked_points()
    vis.destroy_window()

    if picked is None or len(picked) == 0:
        print("No points picked; using full cloud.")
        return None, None

    picked_pts = points[np.array(picked)]
    roi_min = picked_pts.min(axis=0)
    roi_max = picked_pts.max(axis=0)
    print(f"ROI min: {roi_min}, ROI max: {roi_max}")
    return roi_min, roi_max

# ----------------------------
# Center-zone extraction for ICP
# ----------------------------
def extract_center_zone_points(depth_map, rgb_image, intrinsics, extrinsics,
                               conf_map, conf_thresh=0.7, center_ratio=0.6):
    """Back-project only high-confidence points from the image center."""
    h, w = depth_map.shape
    margin_h = int(h * (1 - center_ratio) / 2)
    margin_w = int(w * (1 - center_ratio) / 2)

    center_mask = np.zeros((h, w), dtype=bool)
    center_mask[margin_h:h - margin_h, margin_w:w - margin_w] = True

    valid = center_mask & (conf_map > conf_thresh)
    if not np.any(valid):
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.float32)

    fx, fy = intrinsics[0, 0], intrinsics[1, 1]
    cx, cy = intrinsics[0, 2], intrinsics[1, 2]

    u, v = np.meshgrid(np.arange(w), np.arange(h))
    u_v = u[valid].astype(np.float32)
    v_v = v[valid].astype(np.float32)
    d = depth_map[valid].astype(np.float32)

    x = (u_v - cx) * d / fx
    y = (v_v - cy) * d / fy
    pts_cam = np.stack([x, y, d], axis=-1)

    pts_world = camera_to_world_points(pts_cam, extrinsics, cam2world=EXTRINSICS_ARE_CAM2WORLD)
    cols = rgb_image[valid].reshape(-1, 3).astype(np.float32) / 255.0
    return pts_world, cols

def extract_registration_cloud(prediction, frame_idx, conf_thresh, center_ratio, roi_min=None, roi_max=None):
    pts, _ = extract_center_zone_points(
        prediction.depth[frame_idx],
        prediction.processed_images[frame_idx],
        prediction.intrinsics[frame_idx],
        prediction.extrinsics[frame_idx],
        prediction.conf[frame_idx],
        conf_thresh=conf_thresh,
        center_ratio=center_ratio,
    )
    if roi_min is not None and roi_max is not None and len(pts) > 0:
        pts = pts[np.all((pts >= roi_min) & (pts <= roi_max), axis=1)]
    return pts

# ----------------------------
# ICP
# ----------------------------
def make_registration_pcd(points, voxel_size):
    """Downsample + normals for ICP."""
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
    pcd = pcd.voxel_down_sample(voxel_size=max(voxel_size, 1e-6))
    pcd.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2, max_nn=30))
    return pcd

def icp_refine(source, target, voxel_size):
    """Point-to-plane ICP from identity."""
    return o3d.pipelines.registration.registration_icp(
        source, target,
        max_correspondence_distance=voxel_size * 0.5,
        init=np.eye(4),
        estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPlane(),
        criteria=o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=50),
    )

def preview_two_frame_registration(prediction, frame_a=0, frame_b=1,
                                   conf_thresh=0.7, center_ratio=0.6,
                                   roi_min=None, roi_max=None):
    pts_a = extract_registration_cloud(prediction, frame_a, conf_thresh, center_ratio, roi_min, roi_max)
    pts_b = extract_registration_cloud(prediction, frame_b, conf_thresh, center_ratio, roi_min, roi_max)
    print(f"Two-frame preview: frame {frame_a} ({len(pts_a)} pts) vs frame {frame_b} ({len(pts_b)} pts)")

    if len(pts_a) < 50 or len(pts_b) < 50:
        print("Not enough points for ICP preview.")
        return np.eye(4)

    cols_a = np.tile(np.array([[1.0, 0.3, 0.3]], dtype=np.float32), (len(pts_a), 1))
    cols_b = np.tile(np.array([[0.3, 0.3, 1.0]], dtype=np.float32), (len(pts_b), 1))

    combined = np.vstack((pts_a, pts_b))
    reg_voxel = float(np.ptp(combined, axis=0).max()) / 200.0
    reg_voxel = max(reg_voxel, 1e-4)

    pcd_before = o3d.geometry.PointCloud()
    pcd_before.points = o3d.utility.Vector3dVector(combined)
    pcd_before.colors = o3d.utility.Vector3dVector(np.vstack([cols_a, cols_b]))

    source_pcd = make_registration_pcd(pts_b, reg_voxel)
    target_pcd = make_registration_pcd(pts_a, reg_voxel)

    icp_result = icp_refine(source_pcd, target_pcd, reg_voxel)
    T = icp_result.transformation

    pts_b_h = np.hstack([pts_b, np.ones((len(pts_b), 1), dtype=np.float32)])
    pts_b_aligned = (T @ pts_b_h.T).T[:, :3]

    pcd_after = o3d.geometry.PointCloud()
    pcd_after.points = o3d.utility.Vector3dVector(np.vstack([pts_a, pts_b_aligned]))
    pcd_after.colors = o3d.utility.Vector3dVector(np.vstack([cols_a, cols_b]))

    tree_a = cKDTree(pts_a)
    d_before, _ = tree_a.query(pts_b, k=1)
    d_after, _ = tree_a.query(pts_b_aligned, k=1)
    shift = float(np.linalg.norm(T[:3, 3]))

    print(f"NN mean before: {d_before.mean():.4f} | after: {d_after.mean():.4f}")
    print(f"ICP translation magnitude: {shift:.4f} | fitness: {icp_result.fitness:.4f} | rmse: {icp_result.inlier_rmse:.4f}")

    o3d.visualization.draw_geometries([pcd_before], window_name=f"Before ICP (A=Red, B=Blue)")
    o3d.visualization.draw_geometries([pcd_after], window_name=f"After ICP (A=Red, B=Blue)")
    return T

def register_frames(prediction, per_frame_points, per_frame_colors,
                    conf_thresh=0.7, center_ratio=0.6, max_shift_pct=0.05,
                    roi_min=None, roi_max=None):
    """Refine per-frame alignment with ICP using center-zone points."""
    n_frames = len(per_frame_points)
    if n_frames < 2:
        print("Not enough frames to register")
        return np.vstack(per_frame_points), np.vstack(per_frame_colors)

    all_pts = np.vstack(per_frame_points)
    bbox_extent = all_pts.max(axis=0) - all_pts.min(axis=0)

    reg_voxel = float(np.max(bbox_extent) / 200.0)
    reg_voxel = max(reg_voxel, 1e-4)

    max_translation = float(np.linalg.norm(bbox_extent)) * max_shift_pct
    print(f"Registration voxel size: {reg_voxel:.4f}, max translation: {max_translation:.4f}")
    if roi_min is not None:
        print(f"ROI crop: {roi_min} to {roi_max}")

    target_pts = extract_registration_cloud(prediction, 0, conf_thresh, center_ratio, roi_min, roi_max)
    if len(target_pts) < 50:
        print("Frame 0 registration cloud too small; skipping registration.")
        return np.vstack(per_frame_points), np.vstack(per_frame_colors)

    target_pcd = make_registration_pcd(target_pts, reg_voxel)

    registered_points = [per_frame_points[0]]
    registered_colors = [per_frame_colors[0]]  # FIXED

    for i in range(1, n_frames):
        source_pts = extract_registration_cloud(prediction, i, conf_thresh, center_ratio, roi_min, roi_max)
        if len(source_pts) < 50:
            print(f"Frame {i}: too few reg points ({len(source_pts)} < 50); skipping ICP")
            T = np.eye(4)
        else:
            source_pcd = make_registration_pcd(source_pts, reg_voxel)
            icp_result = icp_refine(source_pcd, target_pcd, reg_voxel)
            T = icp_result.transformation
            shift = float(np.linalg.norm(T[:3, 3]))
            if shift > max_translation:
                print(f"Frame {i}: shift {shift:.4f} > {max_translation:.4f} -- skipping")
                T = np.eye(4)
            else:
                print(f"Frame {i}: shift {shift:.4f} < {max_translation:.4f} -- registering")

        pts_h = np.hstack([per_frame_points[i], np.ones((len(per_frame_points[i]), 1), dtype=np.float32)])
        registered_points.append((T @ pts_h.T).T[:, :3])
        registered_colors.append(per_frame_colors[i])

    merged_points = np.vstack(registered_points)
    merged_colors = np.vstack(registered_colors)
    print(f"Registered point cloud: {len(merged_points)} points")
    return merged_points, merged_colors

# ----------------------------
# Ground plane
# ----------------------------
def segment_ground(points, distance_thresh=0.1, ransac_n=3, num_iterations=1000):
    """Segment dominant plane via Open3D RANSAC."""
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
    plane_model, inlier_indices = pcd.segment_plane(
        distance_threshold=distance_thresh,
        ransac_n=ransac_n,
        num_iterations=num_iterations,
    )
    ground_mask = np.zeros(len(points), dtype=bool)
    ground_mask[inlier_indices] = True
    a, b, c, d = plane_model
    print(f"Ground plane: {a:.3f}x + {b:.3f}y + {c:.3f}z + {d:.3f} = 0")
    print(f"Ground points: {ground_mask.sum()} / {len(points)} ({100 * ground_mask.mean():.1f}%)")
    return ground_mask, plane_model

# ----------------------------
# Clustering
# ----------------------------
def cluster_objects(points, eps=0.1, min_points=10):
    """
    DBSCAN clustering (Open3D). Returns labels:
      0 = noise, 1..N = clusters sorted by size
    """
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
    raw = np.asarray(pcd.cluster_dbscan(eps=eps, min_points=min_points, print_progress=True))

    if raw.max() < 0:
        return np.zeros(len(points), dtype=np.int32)

    valid = raw >= 0
    unique_ids, counts = np.unique(raw[valid], return_counts=True)
    order = np.argsort(-counts)  # desc

    remap = np.zeros(raw.max() + 1, dtype=np.int32)
    for new_id, idx in enumerate(order, start=1):
        remap[unique_ids[idx]] = new_id

    labels = np.zeros(len(raw), dtype=np.int32)
    labels[valid] = remap[raw[valid]]

    print(f"Clusters: {len(order)}, Noise points: {(~valid).sum()}")
    return labels

def merge_seg_labels(ground_mask, cluster_labels, n_points):
    """Ground = 0, non-ground = cluster labels."""
    labels = np.zeros(n_points, dtype=np.int32)
    labels[~ground_mask] = cluster_labels
    return labels

def refine_labels_knn(points, labels, k=15):
    """Smooth noisy boundaries via KNN majority vote."""
    tree = cKDTree(points)
    _, idx = tree.query(points, k=k + 1, workers=-1)
    neigh = labels[idx[:, 1:]]

    n_classes = labels.max() + 1
    # bincount trick
    offsets = (np.arange(len(labels), dtype=np.int64) * n_classes)
    flat = (neigh + offsets[:, None]).ravel()
    votes = np.bincount(flat, minlength=len(labels) * n_classes)
    refined = votes.reshape(len(labels), n_classes).argmax(axis=1).astype(np.int32)

    changed = int((refined != labels).sum())
    print(f"Boundary refinement: {changed} labels changed ({100 * changed / len(labels):.1f}%)")
    return refined

def make_seg_colormap(labels, ground_mask):
    """Ground=brown, noise=gray, clusters=random colors."""
    n_labels = max(int(labels.max()) + 1, 2)
    rng = np.random.RandomState(42)
    cmap = rng.rand(n_labels, 3) * 0.7 + 0.3
    cmap[0] = [0.3, 0.3, 0.3]  # default for label 0 (noise/ground overwritten)
    colors = cmap[labels]
    colors[ground_mask] = [0.55, 0.35, 0.17]
    return colors

# ----------------------------
# Voxelization (move BEFORE calling!)
# ----------------------------
def compute_auto_voxel_size(points, target_voxels=200_000):
    bbox_min = points.min(axis=0)
    bbox_max = points.max(axis=0)
    volume = np.prod(bbox_max - bbox_min)
    voxel_size = (volume / target_voxels) ** (1 / 3.0)
    return float(max(voxel_size, 1e-6))

def voxelize_point_cloud(points, colors, voxel_size=None, labels=None, target_voxels=200_000):
    """
    Structured voxel grid:
      voxel index = floor((p - bbox_min)/voxel_size)
      center = bbox_min + (idx + 0.5)*voxel_size
    """
    if voxel_size is None:
        voxel_size = compute_auto_voxel_size(points, target_voxels)

    bbox_min = points.min(axis=0)
    vidx = np.floor((points - bbox_min) / voxel_size).astype(np.int32)

    uniq, inv, counts = np.unique(vidx, axis=0, return_inverse=True, return_counts=True)
    voxel_centers = bbox_min + (uniq.astype(np.float64) + 0.5) * voxel_size

    n_vox = len(uniq)
    voxel_colors = np.zeros((n_vox, 3), dtype=np.float64)
    np.add.at(voxel_colors, inv, colors.astype(np.float64))
    voxel_colors /= counts[:, None]
    voxel_colors = np.clip(voxel_colors, 0, 1)

    voxel_labels = None
    if labels is not None:
        labels = labels.astype(np.int32)
        n_classes = int(labels.max()) + 1
        vote = np.zeros((n_vox, n_classes), dtype=np.int32)
        np.add.at(vote, (inv, labels), 1)
        voxel_labels = vote.argmax(axis=1).astype(np.int32)

    return voxel_centers, voxel_colors, float(voxel_size), voxel_labels

def create_voxel_cube_mesh(voxel_centers, voxel_colors, voxel_size):
    """Vectorized cube mesh."""
    unit_verts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64) - 0.5

    unit_tris = np.array([
        [0, 2, 1], [0, 3, 2],
        [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4],
        [2, 3, 7], [2, 7, 6],
        [0, 4, 7], [0, 7, 3],
        [1, 2, 6], [1, 6, 5],
    ], dtype=np.int32)

    n = len(voxel_centers)
    all_vertices = (unit_verts * voxel_size) + voxel_centers[:, None, :]
    all_vertices = all_vertices.reshape(-1, 3)

    offsets = (np.arange(n) * 8)[:, None, None]
    all_triangles = (unit_tris + offsets).reshape(-1, 3)

    all_colors = np.repeat(voxel_colors, 8, axis=0)

    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(all_vertices)
    mesh.triangles = o3d.utility.Vector3iVector(all_triangles)
    mesh.vertex_colors = o3d.utility.Vector3dVector(all_colors)
    mesh.compute_vertex_normals()
    return mesh

# ----------------------------
# Export
# ----------------------------
def save_reconstruction_ply(points, colors, filepath, seg_labels=None, ground_mask=None):
    """Export point cloud to binary PLY with optional scalar fields."""
    n = len(points)
    props = [
        "property float x", "property float y", "property float z",
        "property uchar red", "property uchar green", "property uchar blue",
    ]
    dtypes = [('x','f4'),('y','f4'),('z','f4'),('r','u1'),('g','u1'),('b','u1')]

    if seg_labels is not None:
        props.append("property int seg_label")
        dtypes.append(('seg_label', 'i4'))
    if ground_mask is not None:
        props.append("property uchar is_ground")
        dtypes.append(('is_ground', 'u1'))

    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {n}\n"
        + "\n".join(props) + "\nend_header\n"
    )

    arr = np.empty(n, dtype=dtypes)
    arr['x'], arr['y'], arr['z'] = points[:, 0], points[:, 1], points[:, 2]
    rgb = (np.clip(colors, 0, 1) * 255).astype(np.uint8)
    arr['r'], arr['g'], arr['b'] = rgb[:, 0], rgb[:, 1], rgb[:, 2]

    if seg_labels is not None:
        arr['seg_label'] = seg_labels.astype(np.int32)
    if ground_mask is not None:
        arr['is_ground'] = ground_mask.astype(np.uint8)

    with open(filepath, 'wb') as f:
        f.write(header.encode('ascii'))
        arr.tofile(f)

    print(f"Saved {n} points to {filepath}")

# ----------------------------
# MAIN PIPELINE FUNCTIONS
# ----------------------------
def run_device_test(args, paths):
    """
    Mode A: Check device, load model, verify images exist.
    """
    print("\n" + "="*60)
    print("DEVICE TEST MODE")
    print("="*60)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[CHECK] Device available: {device}")
    
    print(f"[CHECK] Loading DA3 model...")
    model, _ = load_da3_model()
    print(f"[SUCCESS] Model loaded successfully")
    
    print(f"[CHECK] Scanning for images in {paths['data']}")
    image_files = load_images_from_folder(paths["data"], extensions=("*.jpg", "*.png", "*.jpeg"))
    
    if len(image_files) == 0:
        raise ValueError(f"ERROR: No images found in {paths['data']}")
    
    print(f"[SUCCESS] Found {len(image_files)} images")
    for i, f in enumerate(image_files[:5], 1):
        print(f"  - {os.path.basename(f)}")
    if len(image_files) > 5:
        print(f"  ... and {len(image_files) - 5} more")
    
    print("\n[DEVICE TEST COMPLETE] All checks passed!\n")

def run_preview_mode(args, paths):
    """
    Mode B: Run inference on 1 image, show depth + confidence + point cloud.
    """
    print("\n" + "="*60)
    print("PREVIEW MODE")
    print("="*60)
    
    print(f"[LOAD] Images from {paths['data']}")
    image_files = load_images_from_folder(paths["data"], extensions=("*.jpg", "*.png", "*.jpeg"))
    
    if len(image_files) == 0:
        raise ValueError(f"ERROR: No images found in {paths['data']}")
    
    # Take only first image
    image_files = image_files[:1]
    print(f"[INFERENCE] Running DA3 on {len(image_files)} image(s)...")
    
    print(f"[LOAD] Loading DA3 model...")
    model, device = load_da3_model()
    print(f"[SUCCESS] Model loaded")
    
    print(f"[INFER] Processing image...")
    prediction = run_da3_inference(model, image_files)
    print(f"[SUCCESS] Inference complete")
    
    print(f"[VIZ] Displaying depth + confidence...")
    visualize_depth_and_confidence(
        prediction.processed_images,
        prediction.depth,
        prediction.conf,
        sample_idx=0
    )
    
    print(f"[PC] Generating point cloud from frame 0...")
    pts, cols = depth_to_point_cloud(
        prediction.depth[0],
        prediction.processed_images[0],
        prediction.intrinsics[0],
        prediction.extrinsics[0],
        prediction.conf[0],
        conf_thresh=args.conf,
    )
    print(f"[SUCCESS] Generated {len(pts)} points")
    print(f"[VIZ] Displaying single-frame point cloud...")
    visualize_point_cloud_open3d(pts, cols, window_name="Preview: Single-Frame Point Cloud")
    
    print("\n[PREVIEW COMPLETE]\n")

def run_default_mode(args, paths):
    """
    Mode C: Full pipeline (N images, merge, clean, register, segment, cluster, voxelize, export).
    """
    print("\n" + "="*60)
    print("DEFAULT MODE: Full Pipeline")
    print("="*60)
    
    print(f"[LOAD] Images from {paths['data']}")
    image_files = load_images_from_folder(paths["data"], extensions=("*.jpg", "*.png", "*.jpeg"))
    
    if len(image_files) == 0:
        raise ValueError(f"ERROR: No images found in {paths['data']}")
    
    # Limit to N images
    image_files = image_files[:args.n_images]
    print(f"[SELECT] Using first {len(image_files)} images")
    
    # LOAD MODEL
    print(f"[LOAD] Loading DA3 model...")
    model, device = load_da3_model()
    print(f"[SUCCESS] Model loaded")
    
    # INFERENCE
    print(f"[INFER] Running DA3 inference on {len(image_files)} image(s)...")
    prediction = run_da3_inference(model, image_files)
    print(f"[SUCCESS] Inference complete")
    
    # MERGE CLOUDS
    print(f"[MERGE] Merging point clouds (conf_thresh={args.conf})...")
    points_3d, colors_3d, per_frame_points, per_frame_colors = merge_point_clouds(
        prediction, conf_thresh=args.conf
    )
    print(f"[SUCCESS] Merged shape: {points_3d.shape}")
    
    print(f"[VIZ] Displaying merged point cloud...")
    visualize_point_cloud_open3d(points_3d, colors_3d, window_name="Full Scene Point Cloud")
    
    # CLEAN
    print(f"[CLEAN] Statistical outlier removal...")
    start = time.time()
    clean_pts_sci, clean_cols_sci = clean_point_cloud_scipy(
        points_3d, colors_3d, nb_neighbors=20, std_ratio=1.0
    )
    elapsed = time.time() - start
    print(f"[SUCCESS] Cleaned shape: {clean_pts_sci.shape} in {elapsed:.2f}s")
    
    print(f"[VIZ] Displaying cleaned point cloud...")
    visualize_point_cloud_open3d(clean_pts_sci, clean_cols_sci, window_name="Cleaned Point Cloud")
    
    # ROI SELECTION (optional)
    print(f"[ROI] Interactive ROI selection (optional)...")
    roi_min, roi_max = interactive_roi_from_picks(clean_pts_sci, clean_cols_sci)
    
    # REGISTRATION
    if len(per_frame_points) > 2:
        print(f"[REG_PREVIEW] Previewing 2-frame registration...")
        _ = preview_two_frame_registration(
            prediction, conf_thresh=0.9, center_ratio=0.5, roi_min=roi_min, roi_max=roi_max
        )
    
    if len(per_frame_points) > 1:
        print(f"[REG] Multi-frame ICP registration...")
        start = time.time()
        reg_points, reg_colors = register_frames(
            prediction, per_frame_points, per_frame_colors,
            conf_thresh=0.9, center_ratio=0.5, max_shift_pct=0.05,
            roi_min=roi_min, roi_max=roi_max
        )
        elapsed = time.time() - start
        print(f"[SUCCESS] Registration complete in {elapsed:.2f}s")
        
        print(f"[CLEAN] Post-registration cleaning...")
        clean_pts_sci, clean_cols_sci = clean_point_cloud_scipy(
            reg_points, reg_colors, nb_neighbors=20, std_ratio=1.0
        )
        print(f"[SUCCESS] Post-reg cleaned shape: {clean_pts_sci.shape}")
        print(f"[VIZ] Displaying registered cloud...")
        visualize_point_cloud_open3d(clean_pts_sci, clean_cols_sci, window_name="Registered Point Cloud")
    else:
        print(f"[SKIP] Registration skipped (only 1 frame)")
    
    # GROUND SEGMENTATION
    print(f"[GROUND] Segmenting ground plane...")
    start = time.time()
    ground_mask, plane_model = segment_ground(clean_pts_sci, distance_thresh=0.1)
    elapsed = time.time() - start
    print(f"[SUCCESS] Ground segmentation complete in {elapsed:.2f}s")
    print(f"[STATS] Ground points: {ground_mask.sum()} / {len(clean_pts_sci)} ({100*ground_mask.mean():.1f}%)")
    
    print(f"[VIZ] Displaying ground plane...")
    ground_vis = clean_cols_sci.copy()
    ground_vis[ground_mask] = [0.55, 0.35, 0.17]
    visualize_point_cloud_open3d(clean_pts_sci, ground_vis, window_name="Ground Plane")
    
    # CLUSTERING
    print(f"[CLUSTER] Extracting non-ground points...")
    non_ground_pts = clean_pts_sci[~ground_mask]
    non_ground_cols = clean_cols_sci[~ground_mask]
    print(f"[INFO] Non-ground points: {len(non_ground_pts)}")
    
    print(f"[CLUSTER] DBSCAN clustering...")
    start = time.time()
    cluster_labels = cluster_objects(non_ground_pts, eps=0.1, min_points=10)
    elapsed = time.time() - start
    print(f"[SUCCESS] Clustering complete in {elapsed:.2f}s")
    
    # SAFETY CHECK: all noise
    n_clusters = int(cluster_labels.max()) if len(cluster_labels) > 0 else 0
    n_noise = (cluster_labels == 0).sum()
    if n_clusters == 0:
        print(f"[WARNING] All points classified as noise! Check eps/min_points parameters.")
    else:
        print(f"[STATS] Clusters: {n_clusters}, Noise points: {n_noise}")
    
    print(f"[VIZ] Displaying clustered objects...")
    n_cl = max(int(cluster_labels.max()) + 1, 2)
    rng = np.random.RandomState(42)
    cl_map = rng.rand(n_cl, 3) * 0.7 + 0.3
    cl_map[0] = [0.3, 0.3, 0.3]
    visualize_point_cloud_open3d(non_ground_pts, cl_map[cluster_labels], window_name="Clustered Objects")
    
    # MERGE LABELS
    print(f"[MERGE] Merging ground + cluster labels...")
    seg_labels = merge_seg_labels(ground_mask, cluster_labels, len(clean_pts_sci))
    print(f"[VIZ] Displaying segmented scene...")
    visualize_point_cloud_open3d(clean_pts_sci, make_seg_colormap(seg_labels, ground_mask), window_name="Segmented Objects")
    
    # REFINE BOUNDARIES
    print(f"[REFINE] KNN boundary refinement...")
    start = time.time()
    seg_labels = refine_labels_knn(clean_pts_sci, seg_labels, k=15)
    elapsed = time.time() - start
    print(f"[SUCCESS] Refinement complete in {elapsed:.2f}s")
    print(f"[VIZ] Displaying refined segmentation...")
    visualize_point_cloud_open3d(clean_pts_sci, make_seg_colormap(seg_labels, ground_mask), 
                                 window_name="Segmented Objects (Refined)")
    
    # VOXELIZATION
    print(f"[VOXEL] Computing auto voxel size...")
    voxel_size = compute_auto_voxel_size(clean_pts_sci, target_voxels=200_000)
    
    # SAFETY CHECK: voxel size
    if voxel_size == 0:
        voxel_size = 1e-6
        print(f"[SAFETY] Voxel size was 0; clamped to {voxel_size:.2e}")
    else:
        print(f"[INFO] Auto voxel size: {voxel_size:.6f}")
    
    print(f"[VOXEL] Voxelizing point cloud...")
    voxel_centers, voxel_colors, _, voxel_labels = voxelize_point_cloud(
        clean_pts_sci, clean_cols_sci, voxel_size=voxel_size, labels=seg_labels
    )
    print(f"[SUCCESS] Voxelized to {len(voxel_centers)} voxels")
    
    print(f"[MESH] Creating voxel mesh...")
    voxel_mesh = create_voxel_cube_mesh(voxel_centers, voxel_colors, voxel_size)
    print(f"[VIZ] Displaying voxel mesh (RGB)...")
    o3d.visualization.draw_geometries([voxel_mesh], window_name="Voxel Mesh (RGB)")
    
    # SEGMENTATION VOXEL VISUALIZATION
    n_vlabels = max(int(voxel_labels.max()) + 1, 2) if voxel_labels is not None else 2
    rng_v = np.random.RandomState(42)
    voxel_label_cmap = rng_v.rand(n_vlabels, 3) * 0.7 + 0.3
    voxel_label_cmap[0] = [0.55, 0.35, 0.17]  # ground-ish
    voxel_label_colors = voxel_label_cmap[voxel_labels] if voxel_labels is not None else voxel_colors
    
    voxel_mesh_seg = create_voxel_cube_mesh(voxel_centers, voxel_label_colors, voxel_size)
    print(f"[VIZ] Displaying voxel mesh (segmentation)...")
    o3d.visualization.draw_geometries([voxel_mesh_seg], window_name="Voxel Mesh (Segmentation Labels)")
    
    # EXPORT
    print(f"[EXPORT] Exporting Gaussian Splatting PLY...")
    from depth_anything_3.utils.export.gs import export_to_gs_ply
    from depth_anything_3.utils.export.glb import export_to_glb
    
    export_dir = paths["results"]
    export_to_gs_ply(prediction, export_dir)
    print(f"[SUCCESS] GS PLY exported to {export_dir}/gs_ply/")
    
    print(f"[EXPORT] Exporting GLB scene...")
    glb_path = export_to_glb(prediction, export_dir)
    print(f"[SUCCESS] GLB scene exported: {glb_path}")
    
    print(f"[EXPORT] Saving reconstruction PLY...")
    ply_path = os.path.join(paths["results"], "reconstruction.ply")
    save_reconstruction_ply(clean_pts_sci, clean_cols_sci, ply_path, 
                            seg_labels=seg_labels, ground_mask=ground_mask)
    
    print(f"[EXPORT] Saving voxel meshes...")
    voxel_rgb_path = os.path.join(paths["results"], "voxel_mesh_rgb.ply")
    o3d.io.write_triangle_mesh(voxel_rgb_path, voxel_mesh)
    print(f"[SUCCESS] Voxel mesh (RGB) saved to {voxel_rgb_path}")
    
    voxel_seg_path = os.path.join(paths["results"], "voxel_mesh_seg.ply")
    o3d.io.write_triangle_mesh(voxel_seg_path, voxel_mesh_seg)
    print(f"[SUCCESS] Voxel mesh (seg) saved to {voxel_seg_path}")
    
    print("\n[PIPELINE COMPLETE]\n")

def main():
    """Main entry point with argument parsing and mode selection."""
    parser = argparse.ArgumentParser(
        description="DA3 3D Reconstruction Pipeline with Testing Modes"
    )
    parser.add_argument("--scene", type=str, default="SAMPLE_SCENE",
                        help="Scene folder name (default: SAMPLE_SCENE)")
    parser.add_argument("--n_images", type=int, default=5,
                        help="Max number of images to process (default: 5)")
    parser.add_argument("--conf", type=float, default=0.4,
                        help="Confidence threshold for point filtering (default: 0.4)")
    parser.add_argument("--device_test", action="store_true",
                        help="Device test mode: check device, load model, verify images")
    parser.add_argument("--preview", action="store_true",
                        help="Preview mode: run inference on 1 image, show depth + PC")
    
    args = parser.parse_args()
    
    # PRINT STARTUP INFO
    print("\n" + "="*60)
    print("3D RECONSTRUCTION PIPELINE")
    print("="*60)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"[INFO] Script location: {script_dir}")
    print(f"[INFO] Current working directory: {os.getcwd()}")
    print(f"[INFO] Scene: {args.scene}")
    print(f"[INFO] N images: {args.n_images}")
    print(f"[INFO] Confidence threshold: {args.conf}")
    
    # SETUP PATHS
    paths = setup_paths(args.scene)
    print(f"[INFO] Data path: {paths['data']}")
    print(f"[INFO] Results path: {paths['results']}")
    
    # VERIFY DATA PATH EXISTS
    if not os.path.exists(paths["data"]):
        raise FileNotFoundError(f"Data path does not exist: {paths['data']}")
    
    # RUN APPROPRIATE MODE
    try:
        if args.device_test:
            run_device_test(args, paths)
        elif args.preview:
            run_preview_mode(args, paths)
        else:
            run_default_mode(args, paths)
    except Exception as e:
        print(f"\n[ERROR] {str(e)}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()