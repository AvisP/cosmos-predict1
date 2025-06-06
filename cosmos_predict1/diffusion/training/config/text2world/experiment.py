# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from hydra.core.config_store import ConfigStore
from megatron.core import parallel_state
from torch.utils.data import DataLoader, DistributedSampler

from cosmos_predict1.diffusion.training.callbacks.iter_speed import IterSpeed
from cosmos_predict1.diffusion.training.callbacks.low_precision import LowPrecisionCallback
from cosmos_predict1.diffusion.training.datasets.dataset_video import Dataset
from cosmos_predict1.diffusion.training.models.model import FSDPDiffusionModel
from cosmos_predict1.utils import log
from cosmos_predict1.utils.callback import ProgressBarCallback
from cosmos_predict1.utils.callbacks.grad_clip import GradClip
from cosmos_predict1.utils.lazy_config import PLACEHOLDER
from cosmos_predict1.utils.lazy_config import LazyCall as L
from cosmos_predict1.utils.lazy_config import LazyDict


def get_sampler(dataset):
    return DistributedSampler(
        dataset,
        num_replicas=parallel_state.get_data_parallel_world_size(),
        rank=parallel_state.get_data_parallel_rank(),
        shuffle=True,
        seed=0,
    )


cs = ConfigStore.instance()

num_frames = 121

# HDVILA example
example_video_dataset_hdvila = L(Dataset)(
    dataset_dir="datasets/hdvila",
    sequence_interval=1,
    num_frames=num_frames,
    video_size=(720, 1280),
    start_frame_interval=1,
)

dataloader_train_hdvila = L(DataLoader)(
    dataset=example_video_dataset_hdvila,
    sampler=L(get_sampler)(dataset=example_video_dataset_hdvila),
    batch_size=1,
    drop_last=True,
)
dataloader_val_hdvila = L(DataLoader)(
    dataset=example_video_dataset_hdvila,
    sampler=L(get_sampler)(dataset=example_video_dataset_hdvila),
    batch_size=1,
    drop_last=True,
)

# Cosmos-NeMo-Assets example
example_video_dataset_cosmos_nemo_assets = L(Dataset)(
    dataset_dir="datasets/cosmos_nemo_assets",
    sequence_interval=1,
    num_frames=num_frames,
    video_size=(720, 1280),
    start_frame_interval=1,
)

dataloader_train_cosmos_nemo_assets = L(DataLoader)(
    dataset=example_video_dataset_cosmos_nemo_assets,
    sampler=L(get_sampler)(dataset=example_video_dataset_cosmos_nemo_assets),
    batch_size=1,
    drop_last=True,
)
dataloader_val_cosmos_nemo_assets = L(DataLoader)(
    dataset=example_video_dataset_cosmos_nemo_assets,
    sampler=L(get_sampler)(dataset=example_video_dataset_cosmos_nemo_assets),
    batch_size=1,
    drop_last=True,
)


text2world_7b_example_hdvila = LazyDict(
    dict(
        defaults=[
            {"override /net": "faditv2_7b"},
            {"override /ckpt_klass": "fsdp"},
            {"override /checkpoint": "local"},
            {"override /vae": "cosmos_diffusion_tokenizer_comp8x8x8"},
            {"override /conditioner": "add_fps_image_size_padding_mask"},
            "_self_",
        ],
        job=dict(
            project="posttraining",
            group="diffusion_text2world",
            name="text2world_7b_example_hdvila",
        ),
        optimizer=dict(
            lr=2 ** (-14.3),  # 2**(-14.3) approx 5e-5
            weight_decay=0.1,
            betas=[0.9, 0.99],
            eps=1e-10,
        ),
        checkpoint=dict(
            save_iter=200,
            broadcast_via_filesystem=False,
            load_path="checkpoints/Cosmos-Predict1-7B-Text2World/model.pt",
            load_training_state=False,
            strict_resume=False,
            keys_not_to_resume=[],
        ),
        trainer=dict(
            max_iter=2000,
            distributed_parallelism="fsdp",
            logging_iter=200,
            callbacks=dict(
                grad_clip=L(GradClip)(
                    model_key="model",
                    fsdp_enabled=True,
                ),
                low_prec=L(LowPrecisionCallback)(config=PLACEHOLDER, trainer=PLACEHOLDER, update_iter=1),
                iter_speed=L(IterSpeed)(
                    every_n=10,
                    hit_thres=0,
                ),
                progress_bar=L(ProgressBarCallback)(),
            ),
            grad_accum_iter=2,
        ),
        model_parallel=dict(
            sequence_parallel=False,
            tensor_model_parallel_size=1,
            context_parallel_size=8,
        ),
        model=dict(
            # Use 16x16x32x40 latent shape for training
            latent_shape=[
                16,  # Latent channel dim
                16,  # Latent temporal dim
                88,  # Latent height dim
                160,  # Latent width dim
            ],
            loss_reduce="mean",
            loss_scale=10.0,
            ema=dict(
                enabled=True,
            ),
            fsdp_enabled=True,
            fsdp=dict(
                policy="block",
                checkpoint=False,
                min_num_params=1024,
                sharding_group_size=32,
                sharding_strategy="hybrid",
            ),
            net=dict(
                in_channels=16,
                extra_per_block_abs_pos_emb=True,
                extra_per_block_abs_pos_emb_type="learnable",
                rope_h_extrapolation_ratio=1,
                rope_w_extrapolation_ratio=1,
                rope_t_extrapolation_ratio=2,
            ),
            vae=dict(pixel_chunk_duration=num_frames),
        ),
        model_obj=L(FSDPDiffusionModel)(
            config=PLACEHOLDER,
            fsdp_checkpointer=PLACEHOLDER,
        ),
        # warming up for first 2500 steps~(when resume from 310000)
        scheduler=dict(
            warm_up_steps=[2500],
            cycle_lengths=[10000000000000],
            f_start=[1.0e-6],
            f_max=[1.0],
            f_min=[1.0],
        ),
        dataloader_train=dataloader_train_hdvila,
        dataloader_val=dataloader_val_hdvila,
    )
)


text2world_14b_example_hdvila = LazyDict(
    dict(
        defaults=[
            {"override /net": "faditv2_14b"},
            {"override /ckpt_klass": "fsdp"},
            {"override /checkpoint": "local"},
            {"override /vae": "cosmos_diffusion_tokenizer_comp8x8x8"},
            {"override /conditioner": "add_fps_image_size_padding_mask"},
            "_self_",
        ],
        job=dict(
            project="posttraining",
            group="diffusion_text2world",
            name="text2world_14b_example_hdvila",
        ),
        optimizer=dict(
            lr=2 ** (-16),
            weight_decay=0.2,
            betas=[0.9, 0.99],
            eps=1e-11,
        ),
        checkpoint=dict(
            save_iter=200,
            broadcast_via_filesystem=False,
            load_path="checkpoints/Cosmos-Predict1-14B-Text2World/model.pt",
            load_training_state=False,
            strict_resume=False,
            keys_not_to_resume=[],
        ),
        trainer=dict(
            max_iter=2000,
            distributed_parallelism="fsdp",
            logging_iter=200,
            callbacks=dict(
                grad_clip=L(GradClip)(
                    model_key="model",
                    fsdp_enabled=True,
                ),
                low_prec=L(LowPrecisionCallback)(config=PLACEHOLDER, trainer=PLACEHOLDER, update_iter=1),
                iter_speed=L(IterSpeed)(
                    every_n=10,
                    hit_thres=0,
                ),
                progress_bar=L(ProgressBarCallback)(),
            ),
        ),
        model_parallel=dict(
            sequence_parallel=False,
            tensor_model_parallel_size=1,
            context_parallel_size=8,
        ),
        model=dict(
            # Use 16x16x32x40 latent shape for training
            latent_shape=[
                16,  # Latent channel dim
                16,  # Latent temporal dim
                88,  # Latent height dim
                160,  # Latent width dim
            ],
            loss_reduce="mean",
            loss_scale=10.0,
            ema=dict(
                enabled=True,
                num=1,
            ),
            fsdp_enabled=True,
            fsdp=dict(
                policy="block",
                checkpoint=False,
                min_num_params=1024,
                sharding_group_size=64,
                sharding_strategy="hybrid",
            ),
            net=dict(
                in_channels=16,
                extra_per_block_abs_pos_emb=True,
                rope_h_extrapolation_ratio=2.0,
                rope_t_extrapolation_ratio=2.0,
                rope_w_extrapolation_ratio=2.0,
                extra_h_extrapolation_ratio=2.0,
                extra_t_extrapolation_ratio=2.0,
                extra_w_extrapolation_ratio=2.0,
                use_memory_save=True,
                extra_per_block_abs_pos_emb_type="learnable",
            ),
            adjust_video_noise=True,
            vae=dict(pixel_chunk_duration=num_frames),
            conditioner=dict(text=dict(dropout_rate=0.0)),
        ),
        model_obj=L(FSDPDiffusionModel)(
            config=PLACEHOLDER,
            fsdp_checkpointer=PLACEHOLDER,
        ),
        # warming up for first 2500 steps~(when resume from 310000)
        scheduler=dict(
            warm_up_steps=[2500],
            cycle_lengths=[90_000],
            f_start=[1.0e-6],
            f_max=[1.0],
            f_min=[1e-1],
        ),
        dataloader_train=dataloader_train_hdvila,
        dataloader_val=dataloader_val_hdvila,
    )
)

text2world_7b_example_cosmos_nemo_assets = LazyDict(
    dict(
        defaults=[
            {"override /net": "faditv2_7b"},
            {"override /ckpt_klass": "fsdp"},
            {"override /checkpoint": "local"},
            {"override /vae": "cosmos_diffusion_tokenizer_comp8x8x8"},
            {"override /conditioner": "add_fps_image_size_padding_mask"},
            "_self_",
        ],
        job=dict(
            project="posttraining",
            group="diffusion_text2world",
            name="text2world_7b_example_cosmos_nemo_assets",
        ),
        optimizer=dict(
            lr=2 ** (-14.3),  # 2**(-14.3) approx 5e-5
            weight_decay=0.1,
            betas=[0.9, 0.99],
            eps=1e-10,
        ),
        checkpoint=dict(
            save_iter=200,
            broadcast_via_filesystem=False,
            load_path="checkpoints/Cosmos-Predict1-7B-Text2World/model.pt",
            load_training_state=False,
            strict_resume=False,
            keys_not_to_resume=[],
        ),
        trainer=dict(
            max_iter=2000,
            distributed_parallelism="fsdp",
            logging_iter=200,
            callbacks=dict(
                grad_clip=L(GradClip)(
                    model_key="model",
                    fsdp_enabled=True,
                ),
                low_prec=L(LowPrecisionCallback)(config=PLACEHOLDER, trainer=PLACEHOLDER, update_iter=1),
                iter_speed=L(IterSpeed)(
                    every_n=10,
                    hit_thres=0,
                ),
                progress_bar=L(ProgressBarCallback)(),
            ),
        ),
        model_parallel=dict(
            sequence_parallel=False,
            tensor_model_parallel_size=1,
            context_parallel_size=8,
        ),
        model=dict(
            # Use 16x16x32x40 latent shape for training
            latent_shape=[
                16,  # Latent channel dim
                16,  # Latent temporal dim
                88,  # Latent height dim
                160,  # Latent width dim
            ],
            loss_reduce="mean",
            ema=dict(
                enabled=True,
            ),
            fsdp_enabled=True,
            fsdp=dict(
                policy="block",
                checkpoint=False,
                min_num_params=1024,
                sharding_group_size=32,
                sharding_strategy="hybrid",
            ),
            net=dict(
                in_channels=16,
                extra_per_block_abs_pos_emb=True,
                extra_per_block_abs_pos_emb_type="learnable",
                rope_h_extrapolation_ratio=1,
                rope_w_extrapolation_ratio=1,
                rope_t_extrapolation_ratio=2,
            ),
            vae=dict(pixel_chunk_duration=num_frames),
        ),
        model_obj=L(FSDPDiffusionModel)(
            config=PLACEHOLDER,
            fsdp_checkpointer=PLACEHOLDER,
        ),
        # warming up for first 2500 steps~(when resume from 310000)
        scheduler=dict(
            warm_up_steps=[2500],
            cycle_lengths=[10000000000000],
            f_start=[1.0e-6],
            f_max=[1.0],
            f_min=[1.0],
        ),
        dataloader_train=dataloader_train_cosmos_nemo_assets,
        dataloader_val=dataloader_val_cosmos_nemo_assets,
    )
)


text2world_14b_example_cosmos_nemo_assets = LazyDict(
    dict(
        defaults=[
            {"override /net": "faditv2_14b"},
            {"override /ckpt_klass": "fsdp"},
            {"override /checkpoint": "local"},
            {"override /vae": "cosmos_diffusion_tokenizer_comp8x8x8"},
            {"override /conditioner": "add_fps_image_size_padding_mask"},
            "_self_",
        ],
        job=dict(
            project="posttraining",
            group="diffusion_text2world",
            name="text2world_14b_example_cosmos_nemo_assets",
        ),
        optimizer=dict(
            lr=2 ** (-16),
            weight_decay=0.2,
            betas=[0.9, 0.99],
            eps=1e-11,
        ),
        checkpoint=dict(
            save_iter=200,
            broadcast_via_filesystem=False,
            load_path="checkpoints/Cosmos-Predict1-14B-Text2World/model.pt",
            load_training_state=False,
            strict_resume=False,
            keys_not_to_resume=[],
        ),
        trainer=dict(
            max_iter=2000,
            distributed_parallelism="fsdp",
            logging_iter=200,
            callbacks=dict(
                grad_clip=L(GradClip)(
                    model_key="model",
                    fsdp_enabled=True,
                ),
                low_prec=L(LowPrecisionCallback)(config=PLACEHOLDER, trainer=PLACEHOLDER, update_iter=1),
                iter_speed=L(IterSpeed)(
                    every_n=10,
                    hit_thres=0,
                ),
                progress_bar=L(ProgressBarCallback)(),
            ),
        ),
        model_parallel=dict(
            sequence_parallel=False,
            tensor_model_parallel_size=1,
            context_parallel_size=8,
        ),
        model=dict(
            # Use 16x16x32x40 latent shape for training
            latent_shape=[
                16,  # Latent channel dim
                16,  # Latent temporal dim
                88,  # Latent height dim
                160,  # Latent width dim
            ],
            loss_reduce="mean",
            loss_scale=10.0,
            ema=dict(
                enabled=True,
                num=1,
            ),
            fsdp_enabled=True,
            fsdp=dict(
                policy="block",
                checkpoint=False,
                min_num_params=1024,
                sharding_group_size=64,
                sharding_strategy="hybrid",
            ),
            net=dict(
                in_channels=16,
                extra_per_block_abs_pos_emb=True,
                rope_h_extrapolation_ratio=2.0,
                rope_t_extrapolation_ratio=2.0,
                rope_w_extrapolation_ratio=2.0,
                extra_h_extrapolation_ratio=2.0,
                extra_t_extrapolation_ratio=2.0,
                extra_w_extrapolation_ratio=2.0,
                use_memory_save=True,
                extra_per_block_abs_pos_emb_type="learnable",
            ),
            adjust_video_noise=True,
            vae=dict(pixel_chunk_duration=num_frames),
            conditioner=dict(text=dict(dropout_rate=0.0)),
        ),
        model_obj=L(FSDPDiffusionModel)(
            config=PLACEHOLDER,
            fsdp_checkpointer=PLACEHOLDER,
        ),
        # warming up for first 2500 steps~(when resume from 310000)
        scheduler=dict(
            warm_up_steps=[2500],
            cycle_lengths=[90_000],
            f_start=[1.0e-6],
            f_max=[1.0],
            f_min=[1e-1],
        ),
        dataloader_train=dataloader_train_cosmos_nemo_assets,
        dataloader_val=dataloader_val_cosmos_nemo_assets,
    )
)


def register_experiments(cs):
    # Register the experiments
    for _item in [
        text2world_7b_example_hdvila,
        text2world_14b_example_hdvila,
        text2world_7b_example_cosmos_nemo_assets,
        text2world_14b_example_cosmos_nemo_assets,
    ]:
        experiment_name = _item["job"]["name"]
        log.info(f"Registering experiment: {experiment_name}")
        cs.store(
            group="experiment",
            package="_global_",
            name=experiment_name,
            node=_item,
        )
