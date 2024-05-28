import torch
import numpy as np
from scipy.spatial.transform import Rotation


def rt2mat(R, T):
    mat = np.eye(4)
    mat[0:3, 0:3] = R
    mat[0:3, 3] = T
    return mat


def skew_sym_mat(x):
    device = x.device
    dtype = x.dtype
    ssm = torch.zeros(3, 3, device=device, dtype=dtype)
    ssm[0, 1] = -x[2]
    ssm[0, 2] = x[1]
    ssm[1, 0] = x[2]
    ssm[1, 2] = -x[0]
    ssm[2, 0] = -x[1]
    ssm[2, 1] = x[0]
    return ssm


def SO3_exp(theta):
    device = theta.device
    dtype = theta.dtype

    W = skew_sym_mat(theta)
    W2 = W @ W
    angle = torch.norm(theta)
    I = torch.eye(3, device=device, dtype=dtype)
    if angle < 1e-5:
        return I + W + 0.5 * W2
    else:
        return (
            I
            + (torch.sin(angle) / angle) * W
            + ((1 - torch.cos(angle)) / (angle**2)) * W2
        )


def V(theta):
    dtype = theta.dtype
    device = theta.device
    I = torch.eye(3, device=device, dtype=dtype)
    W = skew_sym_mat(theta)
    W2 = W @ W
    angle = torch.norm(theta)
    if angle < 1e-5:
        V = I + 0.5 * W + (1.0 / 6.0) * W2
    else:
        V = (
            I
            + W * ((1.0 - torch.cos(angle)) / (angle**2))
            + W2 * ((angle - torch.sin(angle)) / (angle**3))
        )
    return V


def SE3_exp(deltaT):
    dtype = deltaT.dtype
    device = deltaT.device

    rho = deltaT[:3]
    theta = deltaT[3:]
    R = SO3_exp(theta)
    t = V(theta) @ rho

    T = torch.eye(4, device=device, dtype=dtype)
    T[:3, :3] = R
    T[:3, 3] = t
    return T


def update_pose(camera, converged_threshold=5e-4):
    deltaT = torch.cat([camera.cam_trans_delta, camera.cam_rot_delta], axis=0)

    T_w2c = torch.eye(4, device=deltaT.device)
    T_w2c[0:3, 0:3] = camera.R
    T_w2c[0:3, 3] = camera.T

    new_w2c = SE3_exp(deltaT) @ T_w2c

    new_R = new_w2c[0:3, 0:3]
    new_T = new_w2c[0:3, 3]

    converged = deltaT.norm() < converged_threshold
    print(f"deltaT norm: {deltaT.norm()}")
    camera.update_RT(new_R, new_T)

    camera.cam_rot_delta.data.fill_(0)
    camera.cam_trans_delta.data.fill_(0)
    return converged


def interpolate_poses(poses: np.ndarray) -> np.ndarray:
    """ Generates an interpolated pose based on the first two poses in the given array.
    Args:
        poses: An array of poses for the frames (i - 2, i - 1),
               where each pose is represented by a 4x4 transformation matrix.
    Returns:
        A 4x4 numpy ndarray representing the interpolated transformation matrix.
    """
    quat_poses = Rotation.from_matrix(poses[:, :3, :3]).as_quat()
    init_rot = quat_poses[1] + (quat_poses[1] - quat_poses[0])
    init_trans = poses[1, :3, 3] + (poses[1, :3, 3] - poses[0, :3, 3])
    init_transformation = np.eye(4)
    init_transformation[:3, :3] = Rotation.from_quat(init_rot).as_matrix()
    init_transformation[:3, 3] = init_trans
    return init_transformation