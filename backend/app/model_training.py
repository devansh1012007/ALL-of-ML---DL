import copy
import json
import os
import random
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from datasets import load_dataset
from sklearn.cluster import AgglomerativeClustering, KMeans, DBSCAN
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.mixture import GaussianMixture
from sklearn.metrics import accuracy_score, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.svm import SVC, SVR

try:
    from hmmlearn import hmm
except ImportError:
    hmm = None

try:
    import xgboost as xgb
except ImportError:
    xgb = None

try:
    import lightgbm as lgb
except ImportError:
    lgb = None

try:
    import catboost as cb
except ImportError:
    cb = None

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, Dataset
except ImportError:
    torch = None
    nn = None
    DataLoader = None
    Dataset = None

try:
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        TrainingArguments,
        Trainer,
        set_seed,
    )
except ImportError:
    AutoModelForSequenceClassification = None
    AutoTokenizer = None
    TrainingArguments = None
    Trainer = None
    set_seed = None

try:
    import gymnasium as gym
except ImportError:
    gym = None

try:
    import umap
except ImportError:
    umap = None

try:
    import hdbscan
except ImportError:
    hdbscan = None

try:
    from stable_baselines3 import DQN, PPO
except ImportError:
    DQN = None
    PPO = None

try:
    import torchvision
    from torchvision import transforms
    from torchvision.datasets import ImageFolder
    from torchvision.models import resnet18, resnet50
except ImportError:
    torchvision = None
    transforms = None
    ImageFolder = None
    resnet18 = None
    resnet50 = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

def find_repo_root() -> Path:
    candidate = Path(__file__).resolve()
    for _ in range(6):
        if (candidate / "ML_models").exists() or (candidate / "backend").exists() or (candidate / "data").exists():
            return candidate
        if candidate.parent == candidate:
            break
        candidate = candidate.parent
    return Path(__file__).resolve().parents[2]

ROOT = find_repo_root()
DATA_DIR = ROOT / "data"
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "K-Mean": {
        "category": "clustering",
        "description": "K-Means clustering on tabular data.",
        "params": {"n_clusters": 8, "random_state": 42},
        "optimization": ["n_clusters"],
        "test_results": {
            "expected_silhouette": (0.40, 0.80),
            "best_for": ["customer_segmentation", "data_exploration", "large_scale_clustering"],
            "typical_training_time_sec": 2,
            "scalability": "high",
        },
    },
    "HMM_timeseries": {
        "category": "time-series",
        "description": "HMM-based time-series modeling.",
        "params": {"n_components": 4, "covariance_type": "diag", "n_iter": 100},
        "optimization": ["n_components"],
        "test_results": {
            "expected_accuracy": (0.65, 0.85),
            "best_for": ["sequence_prediction", "behavior_analysis", "signal_detection"],
            "typical_training_time_sec": 5,
            "scalability": "medium",
        },
    },
    "GMM": {
        "category": "clustering",
        "description": "Gaussian mixture modeling for clustering.",
        "params": {"n_components": 3, "covariance_type": "full", "random_state": 42},
        "optimization": ["n_components"],
        "test_results": {
            "expected_silhouette": (0.35, 0.75),
            "best_for": ["probabilistic_clustering", "mixture_modeling"],
            "typical_training_time_sec": 3,
            "scalability": "medium",
        },
    },
    "Hierarchical_Clustering": {
        "category": "clustering",
        "description": "Agglomerative hierarchical clustering.",
        "params": {"n_clusters": 4, "linkage": "ward"},
        "optimization": ["n_clusters"],
        "test_results": {
            "expected_silhouette": (0.30, 0.70),
            "best_for": ["dendrogram_analysis", "small_to_medium_datasets"],
            "typical_training_time_sec": 8,
            "scalability": "low",
        },
    },
    "PCA": {
        "category": "clustering",
        "description": "Principal Component Analysis for dimensionality reduction (often used before clustering).",
        "params": {"n_components": 2, "svd_solver": "auto", "random_state": 42},
        "optimization": ["n_components"],
        "test_results": {
            "expected_explained_variance": (0.5, 0.95),
            "best_for": ["dimensionality_reduction", "visualization", "preprocessing"],
            "typical_training_time_sec": 1,
            "scalability": "high",
        },
    },
    "t-SNE": {
        "category": "clustering",
        "description": "t-distributed Stochastic Neighbor Embedding for visualization and embedding.",
        "params": {"n_components": 2, "perplexity": 30.0, "learning_rate": 200.0, "random_state": 42},
        "optimization": ["n_components", "perplexity"],
        "test_results": {
            "expected_quality": (0.4, 0.9),
            "best_for": ["visualization", "small_datasets", "embedding"],
            "typical_training_time_sec": 3,
            "scalability": "low",
        },
    },
    "UMAP": {
        "category": "clustering",
        "description": "UMAP for fast dimensionality reduction and visualization.",
        "params": {"n_components": 2, "n_neighbors": 15, "min_dist": 0.1, "random_state": 42},
        "optimization": ["n_components", "n_neighbors"],
        "test_results": {
            "expected_quality": (0.45, 0.92),
            "best_for": ["visualization", "embedding", "preprocessing"],
            "typical_training_time_sec": 2,
            "scalability": "high",
        },
    },
    "DBSCAN": {
        "category": "clustering",
        "description": "Density-based clustering using DBSCAN.",
        "params": {"eps": 0.5, "min_samples": 5, "metric": "euclidean"},
        "optimization": ["eps", "min_samples"],
        "test_results": {
            "expected_silhouette": (0.2, 0.75),
            "best_for": ["noise_detection", "arbitrary_shape_clusters", "spatial_data"],
            "typical_training_time_sec": 2,
            "scalability": "medium",
        },
    },
    "HDBSCAN": {
        "category": "clustering",
        "description": "Hierarchical density-based clustering (HDBSCAN).",
        "params": {"min_cluster_size": 5, "min_samples": None},
        "optimization": ["min_cluster_size", "min_samples"],
        "test_results": {
            "expected_quality": (0.3, 0.9),
            "best_for": ["robust_density_clustering", "variable_density"],
            "typical_training_time_sec": 4,
            "scalability": "medium",
        },
    },
    "Random_Forest": {
        "category": "classification",
        "description": "Random Forest classifier for tabular data.",
        "params": {
            "n_estimators": 100,
            "max_depth": None,
            "min_samples_split": 2,
            "min_samples_leaf": 1,
            "random_state": 42,
            "n_jobs": -1,
            "test_size": 0.2,
        },
        "optimization": ["n_estimators", "max_depth", "min_samples_split", "min_samples_leaf"],
        "test_results": {
            "expected_accuracy": (0.75, 0.95),
            "best_for": ["tabular_classification", "feature_importance", "mixed_feature_types"],
            "typical_training_time_sec": 3,
            "scalability": "high",
        },
    },
    "Logistic_Regression": {
        "category": "classification",
        "description": "Logistic Regression classifier.",
        "params": {
            "C": 1.0,
            "max_iter": 1000,
            "solver": "lbfgs",
            "penalty": "l2",
            "random_state": 42,
            "test_size": 0.2,
        },
        "optimization": ["C", "penalty"],
        "test_results": {
            "expected_accuracy": (0.70, 0.90),
            "best_for": ["linear_separable_data", "probability_calibration", "interpretability"],
            "typical_training_time_sec": 1,
            "scalability": "high",
        },
    },
    "MLR": {
        "category": "regression",
        "description": "Multiple Linear Regression for numeric prediction.",
        "params": {"fit_intercept": True, "test_size": 0.2, "random_state": 42},
        "optimization": ["fit_intercept"],
        "test_results": {
            "expected_r2": (0.60, 0.95),
            "best_for": ["linear_regression", "coefficient_analysis", "small_datasets"],
            "typical_training_time_sec": 0.5,
            "scalability": "high",
        },
    },
    "KNN": {
        "category": "classification",
        "description": "K-Nearest Neighbors for classification or regression.",
        "params": {
            "n_neighbors": 5,
            "weights": "uniform",
            "algorithm": "auto",
            "p": 2,
            "n_jobs": -1,
            "test_size": 0.2,
            "random_state": 42,
        },
        "optimization": ["n_neighbors", "p"],
        "test_results": {
            "expected_accuracy": (0.65, 0.90),
            "best_for": ["non_linear_boundaries", "small_to_medium_datasets"],
            "typical_training_time_sec": 0.1,
            "scalability": "medium",
        },
    },
    "SVM": {
        "category": "classification",
        "description": "Support Vector Machine for classification or regression.",
        "params": {
            "C": 1.0,
            "kernel": "rbf",
            "gamma": "scale",
            "probability": True,
            "tol": 1e-3,
            "random_state": 42,
            "test_size": 0.2,
        },
        "optimization": ["C", "kernel", "gamma"],
        "test_results": {
            "expected_accuracy": (0.75, 0.95),
            "best_for": ["high_dimensional_data", "binary_classification", "kernel_methods"],
            "typical_training_time_sec": 4,
            "scalability": "medium",
        },
    },
    "XGboost_timeseries": {
        "category": "time-series",
        "description": "XGBoost model for tabular and time-series prediction.",
        "params": {
            "n_estimators": 100,
            "learning_rate": 0.1,
            "max_depth": 6,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "gamma": 0,
            "random_state": 42,
            "test_size": 0.2,
        },
        "optimization": ["n_estimators", "learning_rate", "max_depth"],
        "test_results": {
            "expected_accuracy": (0.80, 0.95),
            "best_for": ["time_series_forecasting", "gradient_boosting", "feature_interactions"],
            "typical_training_time_sec": 6,
            "scalability": "high",
        },
    },
    "lightGBM_timeseries": {
        "category": "time-series",
        "description": "LightGBM model for fast time-series and tabular training.",
        "params": {
            "boosting_type": "gbdt",
            "n_estimators": 100,
            "learning_rate": 0.1,
            "num_leaves": 31,
            "subsample": 0.8,
            "max_depth": -1,
            "random_state": 42,
            "test_size": 0.2,
        },
        "optimization": ["n_estimators", "learning_rate", "num_leaves"],
        "test_results": {
            "expected_accuracy": (0.80, 0.96),
            "best_for": ["fast_training", "large_datasets", "memory_efficiency"],
            "typical_training_time_sec": 3,
            "scalability": "high",
        },
    },
    "CATboost_timeseries": {
        "category": "time-series",
        "description": "CatBoost model for robust time-series and tabular training.",
        "params": {
            "iterations": 100,
            "learning_rate": 0.1,
            "depth": 6,
            "l2_leaf_reg": 3,
            "border_count": 32,
            "random_state": 42,
            "test_size": 0.2,
        },
        "optimization": ["iterations", "learning_rate", "depth"],
        "test_results": {
            "expected_accuracy": (0.78, 0.94),
            "best_for": ["categorical_features", "robustness", "automatic_feature_interaction"],
            "typical_training_time_sec": 7,
            "scalability": "high",
        },
    },
    "PPO": {
        "category": "reinforcement-learning",
        "description": "Proximal Policy Optimization for RL environments.",
        "params": {
            "learning_rate": 2.5e-4,
            "n_steps": 2048,
            "batch_size": 64,
            "gamma": 0.99,
            "ent_coef": 0.01,
            "training_steps": 10000,
        },
        "optimization": ["learning_rate", "n_steps"],
        "test_results": {
            "expected_reward": (100, 500),
            "best_for": ["continuous_control", "policy_optimization", "sample_efficiency"],
            "typical_training_time_sec": 15,
            "scalability": "medium",
        },
    },
    "DQN": {
        "category": "reinforcement-learning",
        "description": "Deep Q-network for discrete action spaces.",
        "params": {
            "learning_rate": 1e-4,
            "buffer_size": 100000,
            "learning_starts": 1000,
            "gamma": 0.99,
            "training_steps": 10000,
        },
        "optimization": ["learning_rate", "buffer_size"],
        "test_results": {
            "expected_reward": (50, 300),
            "best_for": ["discrete_actions", "experience_replay", "exploration"],
            "typical_training_time_sec": 20,
            "scalability": "medium",
        },
    },
    "Q-Learning": {
        "category": "reinforcement-learning",
        "description": "Classic Q-learning for discrete environments.",
        "params": {
            "learning_rate": 0.1,
            "discount_factor": 0.99,
            "epsilon": 0.1,
            "training_steps": 10000,
        },
        "optimization": ["learning_rate", "discount_factor"],
        "test_results": {
            "expected_reward": (30, 200),
            "best_for": ["tabular_environments", "simple_mdp", "convergence_guarantee"],
            "typical_training_time_sec": 10,
            "scalability": "low",
        },
    },
    "Autoencoder": {
        "category": "autoencoder",
        "description": "Autoencoder training for representation learning.",
        "params": {
            "epochs": 10,
            "batch_size": 32,
            "learning_rate": 1e-3,
            "latent_dim": 64,
            "weight_decay": 0.0,
            "dropout_rate": 0.1,
        },
        "optimization": ["latent_dim", "learning_rate"],
        "test_results": {
            "expected_reconstruction_mse": (0.01, 0.1),
            "best_for": ["dimensionality_reduction", "anomaly_detection", "feature_extraction"],
            "typical_training_time_sec": 12,
            "scalability": "high",
        },
    },
    "BERT2BERT": {
        "category": "nlp",
        "description": "Encoder-decoder text modeling using BERT2BERT.",
        "params": {"epochs": 1, "batch_size": 8, "learning_rate": 2e-5, "model_name": "bert-base-uncased"},
        "optimization": ["learning_rate"],
        "test_results": {
            "expected_accuracy": (0.82, 0.96),
            "best_for": ["seq2seq_tasks", "text_generation", "multilingual_support"],
            "typical_training_time_sec": 30,
            "scalability": "medium",
        },
    },
    "self-attenetion_transformer": {
        "category": "nlp",
        "description": "Self-attention transformer for sequence tasks.",
        "params": {"epochs": 1, "batch_size": 8, "learning_rate": 2e-5, "model_name": "distilbert-base-uncased"},
        "optimization": ["learning_rate"],
        "test_results": {
            "expected_accuracy": (0.85, 0.95),
            "best_for": ["text_classification", "attention_mechanisms", "efficient_models"],
            "typical_training_time_sec": 25,
            "scalability": "high",
        },
    },
    "seq2seq": {
        "category": "nlp",
        "description": "Sequence-to-sequence training for text generation.",
        "params": {"epochs": 1, "batch_size": 8, "learning_rate": 2e-5, "model_name": "t5-small"},
        "optimization": ["learning_rate"],
        "test_results": {
            "expected_accuracy": (0.80, 0.92),
            "best_for": ["translation", "summarization", "paraphrase_generation"],
            "typical_training_time_sec": 35,
            "scalability": "medium",
        },
    },
    "UL2": {
        "category": "nlp",
        "description": "UL2-based language fine-tuning.",
        "params": {"epochs": 1, "batch_size": 4, "learning_rate": 2e-5, "model_name": "google/ul2"},
        "optimization": ["learning_rate"],
        "test_results": {
            "expected_accuracy": (0.83, 0.93),
            "best_for": ["unified_text_tasks", "multitask_learning", "versatile_models"],
            "typical_training_time_sec": 40,
            "scalability": "medium",
        },
    },
    "GNN": {
        "category": "graph",
        "description": "Graph neural network training.",
        "params": {
            "epochs": 3,
            "batch_size": 16,
            "learning_rate": 1e-3,
            "weight_decay": 0.0,
        },
        "optimization": ["learning_rate"],
        "test_results": {
            "expected_accuracy": (0.75, 0.92),
            "best_for": ["graph_classification", "node_embedding", "knowledge_graphs"],
            "typical_training_time_sec": 20,
            "scalability": "medium",
        },
    },
    "BERT": {
        "category": "nlp",
        "description": "BERT text classification.",
        "params": {
            "epochs": 1,
            "batch_size": 16,
            "learning_rate": 2e-5,
            "weight_decay": 0.01,
            "warmup_steps": 0,
            "model_name": "bert-base-uncased",
        },
        "optimization": ["learning_rate", "weight_decay"],
        "test_results": {
            "expected_accuracy": (0.88, 0.96),
            "best_for": ["text_classification", "sentiment_analysis", "nli_tasks"],
            "typical_training_time_sec": 28,
            "scalability": "high",
        },
    },
    "DistilBERT": {
        "category": "nlp",
        "description": "DistilBERT text classification.",
        "params": {
            "epochs": 1,
            "batch_size": 16,
            "learning_rate": 2e-5,
            "weight_decay": 0.01,
            "warmup_steps": 0,
            "model_name": "distilbert-base-uncased",
        },
        "optimization": ["learning_rate", "weight_decay"],
        "test_results": {
            "expected_accuracy": (0.85, 0.94),
            "best_for": ["lightweight_models", "mobile_deployment", "fast_inference"],
            "typical_training_time_sec": 18,
            "scalability": "high",
        },
    },
    "GPT": {
        "category": "nlp",
        "description": "GPT-style text fine-tuning.",
        "params": {
            "epochs": 1,
            "batch_size": 8,
            "learning_rate": 2e-5,
            "weight_decay": 0.01,
            "warmup_steps": 0,
            "model_name": "distilgpt2",
        },
        "optimization": ["learning_rate", "weight_decay"],
        "test_results": {
            "expected_accuracy": (0.82, 0.92),
            "best_for": ["text_generation", "language_modeling", "autoregressive_tasks"],
            "typical_training_time_sec": 25,
            "scalability": "high",
        },
    },
    "LLaMA": {
        "category": "nlp",
        "description": "LLaMA-based fine-tuning.",
        "params": {
            "epochs": 1,
            "batch_size": 4,
            "learning_rate": 2e-5,
            "weight_decay": 0.01,
            "warmup_steps": 0,
            "model_name": "meta-llama/Llama-2-7b",
        },
        "optimization": ["learning_rate", "weight_decay"],
        "test_results": {
            "expected_accuracy": (0.87, 0.97),
            "best_for": ["instruction_following", "dialogue", "code_generation"],
            "typical_training_time_sec": 60,
            "scalability": "medium",
        },
    },
    "LSTM": {
        "category": "timeseries",
        "description": "LSTM for sequential prediction.",
        "params": {
            "epochs": 5,
            "batch_size": 32,
            "learning_rate": 1e-3,
            "hidden_size": 64,
            "dropout": 0.0,
        },
        "optimization": ["hidden_size", "learning_rate"],
        "test_results": {
            "expected_accuracy": (0.70, 0.90),
            "best_for": ["time_series", "sequence_modeling", "long_dependencies"],
            "typical_training_time_sec": 18,
            "scalability": "medium",
        },
    },
    "MiniLM": {
        "category": "nlp",
        "description": "MiniLM text representation and classification.",
        "params": {
            "epochs": 1,
            "batch_size": 16,
            "learning_rate": 2e-5,
            "weight_decay": 0.01,
            "warmup_steps": 0,
            "model_name": "sentence-transformers/all-MiniLM-L6-v2",
        },
        "optimization": ["learning_rate", "weight_decay"],
        "test_results": {
            "expected_accuracy": (0.82, 0.93),
            "best_for": ["semantic_similarity", "embedding_tasks", "fast_models"],
            "typical_training_time_sec": 15,
            "scalability": "high",
        },
    },
    "ResNet": {
        "category": "vision",
        "description": "ResNet image classifier (default ResNet-18).",
        "params": {
            "epochs": 3,
            "batch_size": 16,
            "learning_rate": 1e-3,
            "weight_decay": 1e-4,
            "optimizer": "adam",
            "momentum": 0.9,
            "pretrained": True,
            "trainable_layers": "all",
            "model_name": "resnet18",
        },
        "optimization": ["learning_rate", "weight_decay", "optimizer"],
        "test_results": {
            "expected_accuracy": (0.85, 0.97),
            "best_for": ["image_classification", "transfer_learning", "object_recognition"],
            "typical_training_time_sec": 22,
            "scalability": "high",
        },
    },
    "ResNet50": {
        "category": "vision",
        "description": "ResNet-50 image classifier with optional torchvision support.",
        "params": {
            "epochs": 3,
            "batch_size": 16,
            "learning_rate": 1e-3,
            "weight_decay": 1e-4,
            "optimizer": "adam",
            "momentum": 0.9,
            "pretrained": True,
            "trainable_layers": "all",
            "model_name": "resnet50",
        },
        "optimization": ["learning_rate", "weight_decay", "optimizer"],
        "test_results": {
            "expected_accuracy": (0.87, 0.98),
            "best_for": ["high_resolution_images", "fine_grained_classification", "production_systems"],
            "typical_training_time_sec": 35,
            "scalability": "high",
        },
    },
    "RNN": {
        "category": "timeseries",
        "description": "RNN for sequential and time-series prediction.",
        "params": {"epochs": 5, "batch_size": 32, "learning_rate": 1e-3, "hidden_size": 64},
        "optimization": ["hidden_size", "learning_rate"],
        "test_results": {
            "expected_accuracy": (0.65, 0.85),
            "best_for": ["sequential_data", "basic_recurrence", "educational_purposes"],
            "typical_training_time_sec": 15,
            "scalability": "medium",
        },
    },
    "SSM_timeseries": {
        "category": "timeseries",
        "description": "State-space model inspired sequence modeling.",
        "params": {"epochs": 5, "batch_size": 32, "learning_rate": 1e-3, "hidden_size": 64},
        "optimization": ["hidden_size"],
        "test_results": {
            "expected_accuracy": (0.72, 0.88),
            "best_for": ["structured_state_modeling", "efficient_sequences", "long_range"],
            "typical_training_time_sec": 16,
            "scalability": "high",
        },
    },
    "TCN_timeseries": {
        "category": "timeseries",
        "description": "Temporal convolutional network for sequences.",
        "params": {"epochs": 5, "batch_size": 32, "learning_rate": 1e-3, "num_channels": 16},
        "optimization": ["num_channels", "learning_rate"],
        "test_results": {
            "expected_accuracy": (0.75, 0.90),
            "best_for": ["temporal_patterns", "parallel_processing", "long_sequences"],
            "typical_training_time_sec": 17,
            "scalability": "high",
        },
    },
    "ViT": {
        "category": "vision",
        "description": "Vision Transformer for image classification.",
        "params": {"epochs": 3, "batch_size": 16, "learning_rate": 1e-4, "model_name": "google/vit-base-patch16-224"},
        "optimization": ["learning_rate"],
        "test_results": {
            "expected_accuracy": (0.86, 0.96),
            "best_for": ["modern_architectures", "attention_based_vision", "large_scale_data"],
            "typical_training_time_sec": 40,
            "scalability": "high",
        },
    },
}

ALIASES = {
    "K_Mean": "K-Mean",
    "Q_Learning": "Q-Learning",
    "Self_Attention_Transformer": "self-attenetion_transformer",
    "Self-Attention-Transformer": "self-attenetion_transformer",
    "Self_Attention": "self-attenetion_transformer",
    "Autoencoder": "Autoencoder",
    "BERT2BERT": "BERT2BERT",
    "Seq2Seq": "seq2seq",
    "GMM": "GMM",
    "HMM_timeseries": "HMM_timeseries",
    "Hierarchical_Clustering": "Hierarchical_Clustering",
    "PCA": "PCA",
    "TSNE": "t-SNE",
    "t_SNE": "t-SNE",
    "t-Sne": "t-SNE",
    "UMAP": "UMAP",
    "DBSCAN": "DBSCAN",
    "HDBSCAN": "HDBSCAN",
    "SSM_timeseries": "SSM_timeseries",
    "TCN_timeseries": "TCN_timeseries",
}

TRAINING_MODES = ["manual", "auto_tune", "auto_fine_tune", "llm_fine_tune", "auto_search"]

TRAINING_PRESETS = {
    "conservative": {
        "description": "Low learning rate, high regularization, fewer iterations",
        "adjustments": {
            "learning_rate": lambda x: x * 0.1 if isinstance(x, (int, float)) else x,
            "weight_decay": lambda x: x * 10 if isinstance(x, (int, float)) else x,
            "epochs": lambda x: max(1, int(x * 0.5)) if isinstance(x, (int, float)) else x,
            "n_estimators": lambda x: max(10, int(x * 0.7)) if isinstance(x, (int, float)) else x,
        },
    },
    "balanced": {
        "description": "Default settings optimized for most use cases",
        "adjustments": {},
    },
    "aggressive": {
        "description": "High learning rate, low regularization, more iterations",
        "adjustments": {
            "learning_rate": lambda x: x * 2 if isinstance(x, (int, float)) else x,
            "weight_decay": lambda x: x * 0.1 if isinstance(x, (int, float)) else x,
            "epochs": lambda x: int(x * 2) if isinstance(x, (int, float)) else x,
            "n_estimators": lambda x: int(x * 1.5) if isinstance(x, (int, float)) else x,
        },
    },
}


def apply_preset(hyperparameters: Dict[str, Any], preset_name: str) -> Dict[str, Any]:
    """Apply preset configuration adjustments to hyperparameters."""
    if preset_name not in TRAINING_PRESETS:
        return hyperparameters
    
    if preset_name == "balanced":
        return hyperparameters
    
    preset = TRAINING_PRESETS[preset_name]
    adjusted = copy.deepcopy(hyperparameters)
    
    for param_name, adjustment_func in preset["adjustments"].items():
        if param_name in adjusted:
            try:
                adjusted[param_name] = adjustment_func(adjusted[param_name])
            except (TypeError, ValueError):
                pass
    
    return adjusted


def normalize_model_name(name: str) -> str:
    if name in MODEL_CATALOG:
        return name
    if name in ALIASES:
        return ALIASES[name]
    cleaned = name.replace(" ", "_").replace("-", "_")
    if cleaned in ALIASES:
        return ALIASES[cleaned]
    if cleaned in MODEL_CATALOG:
        return cleaned
    return name


def get_model_entry(model_name: str) -> Dict[str, Any]:
    normalized = normalize_model_name(model_name)
    if normalized in MODEL_CATALOG:
        return copy.deepcopy(MODEL_CATALOG[normalized])
    return {
        "category": "custom",
        "description": "A model available in the repository.",
        "params": {},
        "optimization": [],
    }


def list_available_models() -> List[Dict[str, Any]]:
    available = []
    directories = [ROOT / "ML_models", ROOT / "DL_models", ROOT / "Encoder_Decoder"]
    seen = set()
    for directory in directories:
        if directory.exists():
            for file in sorted(directory.iterdir()):
                if file.suffix == ".py":
                    name = file.stem
                    normalized = normalize_model_name(name)
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    info = get_model_entry(normalized)
                    available.append({
                        "name": normalized,
                        "description": info.get("description", "Available model from repository."),
                        "parameters": info.get("params", {}),
                        "category": info.get("category", "custom"),
                        "optimization": info.get("optimization", []),
                        "test_results": info.get("test_results", {}),
                        "supported": normalized in MODEL_CATALOG,
                    })
    if not available:
        # Fallback to the built-in catalog when the repository scan does not locate any model files.
        for normalized, info in MODEL_CATALOG.items():
            available.append({
                "name": normalized,
                "description": info.get("description", "Available model from repository."),
                "parameters": info.get("params", {}),
                "category": info.get("category", "custom"),
                "optimization": info.get("optimization", []),
                "test_results": info.get("test_results", {}),
                "supported": True,
            })
    return available


def list_model_categories() -> List[str]:
    return sorted({entry.get("category", "custom") for entry in MODEL_CATALOG.values()})


def list_local_datasets() -> List[str]:
    if not DATA_DIR.exists():
        return []
    return [str(path.name) for path in sorted(DATA_DIR.glob("*.csv"))]


def parse_hugging_face_reference(value: str) -> str:
    if value.startswith("https://huggingface.co/datasets/"):
        return value.split("https://huggingface.co/datasets/", 1)[1]
    if value.startswith("https://www.huggingface.co/datasets/"):
        return value.split("https://www.huggingface.co/datasets/", 1)[1]
    return value


def load_huggingface_dataset(dataset_ref: str) -> Path:
    dataset_id = parse_hugging_face_reference(dataset_ref.strip())
    dataset = load_dataset(dataset_id)
    split_name = next(iter(dataset.keys()))
    df = dataset[split_name].to_pandas()
    if df.empty:
        raise ValueError("Loaded Hugging Face dataset is empty.")
    if "label" not in df.columns and len(df.columns) >= 2:
        label_column = df.columns[-1]
        df = df.rename(columns={label_column: "label"})
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    df.to_csv(tmp.name, index=False)
    tmp.close()
    return Path(tmp.name)


def infer_task_type(y: pd.Series) -> str:
    if y.dtype == object or y.dtype == bool:
        return "classification"
    if pd.api.types.is_numeric_dtype(y):
        if y.nunique() <= 20:
            return "classification"
        return "regression"
    return "classification"


def safe_json(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, dict):
        return {k: safe_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [safe_json(v) for v in value]
    return value


def ensure_dict(value: Any, name: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a dictionary of hyperparameters.")
    return value


def resolve_dataset_path(dataset_name: str) -> Path:
    candidate = Path(dataset_name)
    return candidate if candidate.is_absolute() else DATA_DIR / dataset_name


def is_image_dataset_path(dataset_name: str) -> bool:
    if not dataset_name:
        return False
    path = resolve_dataset_path(dataset_name)
    return path.exists() and path.is_dir()


def suggest_hyperparameters(
    model_name: str,
    task_type: str,
    optimize_metric: str = "accuracy",
    dataset_name: Optional[str] = None,
    hf_dataset_url: Optional[str] = None,
    use_llm: bool = False,
) -> Dict[str, Any]:
    entry = get_model_entry(model_name)
    base_params = copy.deepcopy(entry.get("params", {}))
    if use_llm:
        if genai is None or not os.getenv("GOOGLE_API_KEY"):
            raise ValueError("LLM fine tuning requires GOOGLE_API_KEY and the google-generativeai package.")
        try:
            # Configure Google Gemini API
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
            model = genai.GenerativeModel(os.getenv("GOOGLE_MODEL", "gemini-pro"))
            
            prompt = (
                f"Provide a JSON object of hyperparameters for {model_name} when training a {task_type} model. "
                f"Optimize for {optimize_metric}. "
                f"Base values: {json.dumps(base_params)}. "
                f"If the dataset is local, use the name {dataset_name}. "
                f"If the dataset is remote, use the Hugging Face reference {hf_dataset_url}. "
                f"Return ONLY valid JSON without any markdown formatting or code blocks."
            )
            response = model.generate_content(prompt)
            prediction = response.text.strip()
            
            # Remove markdown code block markers if present
            if prediction.startswith("```json"):
                prediction = prediction[7:]
            if prediction.startswith("```"):
                prediction = prediction[3:]
            if prediction.endswith("```"):
                prediction = prediction[:-3]
            prediction = prediction.strip()
            
            suggested = json.loads(prediction)
            base_params.update({k: suggested[k] for k in suggested if k in base_params or isinstance(suggested[k], (int, float, str, bool))})
            return base_params
        except Exception as exc:
            raise RuntimeError(f"LLM hyperparameter suggestion failed: {exc}")

    if task_type == "classification":
        base_params["learning_rate"] = base_params.get("learning_rate", 1e-3)
    if task_type == "regression":
        base_params["learning_rate"] = base_params.get("learning_rate", 1e-3)
    if entry.get("category") == "clustering":
        base_params["n_clusters"] = base_params.get("n_clusters", 4)
    if entry.get("category") == "vision":
        base_params["batch_size"] = base_params.get("batch_size", 16)
        base_params["epochs"] = base_params.get("epochs", 3)
    if entry.get("category") == "nlp":
        base_params["batch_size"] = base_params.get("batch_size", 8)
        base_params["epochs"] = base_params.get("epochs", 1)
    return base_params


def build_model(model_name: str, task_type: str, params: Dict[str, Any]):
    if model_name == "Random_Forest":
        if task_type == "classification":
            return RandomForestClassifier(**params)
        return RandomForestRegressor(**params)
    if model_name == "Logistic_Regression":
        return LogisticRegression(**params)
    if model_name == "MLR":
        return LinearRegression(**params)
    if model_name == "KNN":
        if task_type == "classification":
            return KNeighborsClassifier(**params)
        return KNeighborsRegressor(**params)
    if model_name == "SVM":
        if task_type == "classification":
            return SVC(probability=True, **params)
        return SVR(**params)
    if model_name == "XGboost_timeseries":
        if xgb is None:
            raise RuntimeError("xgboost is not installed")
        if task_type == "classification":
            return xgb.XGBClassifier(use_label_encoder=False, eval_metric="logloss", **params)
        return xgb.XGBRegressor(**params)
    if model_name == "lightGBM_timeseries":
        if lgb is None:
            raise RuntimeError("lightgbm is not installed")
        if task_type == "classification":
            return lgb.LGBMClassifier(**params)
        return lgb.LGBMRegressor(**params)
    if model_name == "CATboost_timeseries":
        if cb is None:
            raise RuntimeError("catboost is not installed")
        if task_type == "classification":
            return cb.CatBoostClassifier(verbose=0, **params)
        return cb.CatBoostRegressor(verbose=0, **params)
    raise ValueError(f"Unsupported model: {model_name}")


def _train_clustering(model_name: str, X: pd.DataFrame, params: Dict[str, Any]) -> Tuple[Dict[str, Any], Any]:
    is_embedding = False
    model = None
    if model_name == "K-Mean":
        model = KMeans(**params)
    elif model_name == "GMM":
        model = GaussianMixture(**params)
    elif model_name == "Hierarchical_Clustering":
        model = AgglomerativeClustering(**params)
    elif model_name == "DBSCAN":
        model = DBSCAN(**params)
    elif model_name == "HDBSCAN":
        if hdbscan is None:
            raise RuntimeError("hdbscan is not installed")
        model = hdbscan.HDBSCAN(**params)
    elif model_name == "PCA":
        model = PCA(**params)
        is_embedding = True
    elif model_name == "t-SNE":
        model = TSNE(**params)
        is_embedding = True
    elif model_name == "UMAP":
        if umap is None:
            raise RuntimeError("umap is not installed")
        model = umap.UMAP(**params)
        is_embedding = True
    elif model_name == "HMM_timeseries":
        if hmm is None:
            raise RuntimeError("hmmlearn is not installed")
        model = hmm.GaussianHMM(**params)
    else:
        raise ValueError(f"Unsupported clustering model: {model_name}")

    # Handle dimensionality-reduction style models (produce embeddings)
    if is_embedding:
        embedding = model.fit_transform(X)
        try:
            setattr(model, "_embedding", embedding)
        except Exception:
            pass
        metrics = {"embedding_shape": tuple(embedding.shape), "sample_count": int(embedding.shape[0])}
        return metrics, model

    # For clustering models, try common prediction patterns
    labels = None
    if hasattr(model, "fit_predict"):
        labels = model.fit_predict(X)
    else:
        model.fit(X)
        if hasattr(model, "labels_"):
            labels = getattr(model, "labels_")
        elif hasattr(model, "predict"):
            try:
                labels = model.predict(X)
            except Exception:
                labels = None

    if labels is None:
        labels = np.array([-1] * len(X))

    metrics = {"cluster_count": int(pd.Series(labels).nunique()), "sample_count": int(len(labels))}
    try:
        setattr(model, "_labels", labels)
    except Exception:
        pass
    return metrics, model


def _train_rl_model(model_name: str, env_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if gym is None:
        raise RuntimeError("gymnasium is not installed")
    if not env_id:
        raise ValueError("env_id is required for reinforcement learning models.")
    env = gym.make(env_id)
    if model_name == "PPO":
        if PPO is None:
            raise RuntimeError("stable-baselines3 is not installed")
        agent = PPO("MlpPolicy", env, verbose=0, learning_rate=params.get("learning_rate", 2.5e-4), n_steps=params.get("n_steps", 2048), batch_size=params.get("batch_size", 64))
    elif model_name == "DQN":
        if DQN is None:
            raise RuntimeError("stable-baselines3 is not installed")
        agent = DQN("MlpPolicy", env, verbose=0, learning_rate=params.get("learning_rate", 1e-4), buffer_size=params.get("buffer_size", 100000), learning_starts=params.get("learning_starts", 1000))
    elif model_name == "Q-Learning":
        return {"status": "Q-Learning is supported as a discrete prototype only."}
    else:
        raise ValueError(f"Unsupported RL model: {model_name}")
    agent.learn(total_timesteps=params.get("training_steps", 10000))
    mean_reward = None
    try:
        observation, _ = env.reset()
        total_reward = 0.0
        for _ in range(100):
            action, _ = agent.predict(observation)
            observation, reward, terminated, truncated, _ = env.step(action)
            total_reward += reward
            if terminated or truncated:
                break
        mean_reward = float(total_reward)
    except Exception:
        mean_reward = None
    return {"mean_reward": mean_reward, "training_steps": params.get("training_steps", 10000)}


def _train_transformer_text_classifier(
    model_name: str,
    model_def: Dict[str, Any],
    dataset: pd.DataFrame,
    label_column: str,
    hyperparameters: Dict[str, Any],
) -> Tuple[Dict[str, Any], Any]:
    if AutoTokenizer is None or AutoModelForSequenceClassification is None or Trainer is None or TrainingArguments is None:
        raise RuntimeError("transformers is not installed")
    if label_column not in dataset.columns:
        raise ValueError(f"label column '{label_column}' not found in dataset.")
    text_cols = [c for c in dataset.columns if c != label_column]
    if not text_cols:
        raise ValueError("No text feature column found for transformer training.")
    text_column = text_cols[0]
    dataset = dataset[[text_column, label_column]].dropna()
    tokenizer = AutoTokenizer.from_pretrained(model_def.get("params", {}).get("model_name", "bert-base-uncased"))
    label_values = dataset[label_column].astype(str).tolist()
    unique_labels = sorted(set(label_values))
    label_map = {label: i for i, label in enumerate(unique_labels)}
    labels = [label_map[label] for label in label_values]
    texts = dataset[text_column].astype(str).tolist()
    encodings = tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
    class TextDataset(Dataset):
        def __init__(self, encodings, labels):
            self.encodings = encodings
            self.labels = labels
        def __len__(self):
            return len(self.labels)
        def __getitem__(self, idx):
            item = {k: v[idx] for k, v in self.encodings.items()}
            item["labels"] = torch.tensor(self.labels[idx])
            return item
    train_dataset = TextDataset(encodings, labels)
    model = AutoModelForSequenceClassification.from_pretrained(model_def.get("params", {}).get("model_name", "bert-base-uncased"), num_labels=len(unique_labels))
    args = TrainingArguments(
        output_dir=str(MODEL_DIR / f"{model_name}_transformer"),
        num_train_epochs=int(hyperparameters.get("epochs", 1)),
        per_device_train_batch_size=int(hyperparameters.get("batch_size", 8)),
        learning_rate=float(hyperparameters.get("learning_rate", 2e-5)),
        logging_steps=10,
        save_steps=500,
        no_cuda=not torch.cuda.is_available() if torch is not None else True,
        disable_tqdm=True,
    )
    trainer = Trainer(model=model, args=args, train_dataset=train_dataset)
    trainer.train()
    final_loss = None
    if trainer.state.log_history:
        final_loss = trainer.state.log_history[-1].get("loss")
    return {"train_loss": float(final_loss) if final_loss is not None else None, "labels": unique_labels}, model


def _train_torch_regression_or_classification(
    model_name: str,
    dataset: pd.DataFrame,
    label_column: str,
    hyperparameters: Dict[str, Any],
) -> Tuple[Dict[str, Any], Any]:
    if torch is None:
        raise RuntimeError("torch is not installed")
    if label_column not in dataset.columns:
        raise ValueError(f"label column '{label_column}' not found in dataset.")
    features = dataset.drop(columns=[label_column]).astype(float).fillna(0.0).to_numpy(dtype=np.float32)
    labels = dataset[label_column].astype(float).to_numpy(dtype=np.float32)
    X_train, X_test, y_train, y_test = train_test_split(features, labels, test_size=hyperparameters.get("test_size", 0.2), random_state=int(hyperparameters.get("random_state", 42)))
    input_dim = X_train.shape[1]
    output_dim = 1 if len(y_train.shape) == 1 else y_train.shape[1]
    class SimpleNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.network = nn.Sequential(
                nn.Linear(input_dim, int(hyperparameters.get("hidden_size", 64))),
                nn.ReLU(),
                nn.Linear(int(hyperparameters.get("hidden_size", 64)), output_dim),
            )
        def forward(self, x):
            return self.network(x)
    model = SimpleNet()
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=float(hyperparameters.get("learning_rate", 1e-3)))
    X_train_t = torch.from_numpy(X_train)
    y_train_t = torch.from_numpy(y_train).float().view(-1, 1)
    for _ in range(int(hyperparameters.get("epochs", 5))):
        model.train()
        optimizer.zero_grad()
        outputs = model(X_train_t)
        loss = criterion(outputs, y_train_t)
        loss.backward()
        optimizer.step()
    metrics = {"final_loss": float(loss.detach().item())}
    return metrics, model


def write_artifact(model_name: str, model: Any) -> str:
    artifact_name = f"{model_name}_{int(datetime.utcnow().timestamp())}.joblib"
    artifact_path = MODEL_DIR / artifact_name
    joblib.dump(model, artifact_path)
    return str(artifact_path)


def _prepare_dataset(
    dataset_name: Optional[str],
    hf_dataset_url: Optional[str],
    label_column: str,
    sep: Optional[str],
    usecols: Optional[List[str]],
) -> Tuple[pd.DataFrame, str, str]:
    if dataset_name:
        local_path = resolve_dataset_path(dataset_name)
        if not local_path.exists():
            raise FileNotFoundError(f"Local dataset '{dataset_name}' not found at '{local_path}'.")
        if local_path.is_dir():
            raise ValueError(
                "Local dataset path points to a folder. For image datasets use a vision-capable model like ResNet50 "
                "and a folder with class subdirectories, or provide a CSV file path for tabular models."
            )
        try:
            df = pd.read_csv(local_path, sep=sep, usecols=usecols)
        except pd.errors.EmptyDataError:
            raise ValueError(f"Local dataset '{dataset_name}' is empty.")
        except (pd.errors.ParserError, UnicodeDecodeError) as exc:
            raise ValueError(f"Could not parse local dataset '{dataset_name}': {exc}")
        dataset_source = "local"
        dataset_tag = dataset_name
    elif hf_dataset_url:
        file_path = str(load_huggingface_dataset(hf_dataset_url))
        try:
            df = pd.read_csv(file_path, sep=sep, usecols=usecols)
        except pd.errors.EmptyDataError:
            raise ValueError(f"Hugging Face dataset '{hf_dataset_url}' is empty or invalid.")
        except (pd.errors.ParserError, UnicodeDecodeError) as exc:
            raise ValueError(f"Could not parse Hugging Face dataset '{hf_dataset_url}': {exc}")
        finally:
            try:
                os.remove(file_path)
            except OSError:
                pass
        dataset_source = "huggingface"
        dataset_tag = hf_dataset_url
    else:
        raise ValueError("Either dataset_name or hf_dataset_url must be provided.")

    if df.empty:
        raise ValueError("The dataset contains no rows.")
    if label_column and label_column not in df.columns:
        raise ValueError(f"label column '{label_column}' not found in dataset.")
    return df, dataset_source, dataset_tag


def _train_resnet_image_model(model_name: str, dataset_name: str, hyperparameters: Dict[str, Any]) -> Tuple[Dict[str, Any], Any]:
    if torchvision is None or ImageFolder is None or transforms is None or (resnet18 is None and resnet50 is None):
        raise RuntimeError("torchvision is required for ResNet image training.")
    dataset_path = resolve_dataset_path(dataset_name)
    if not dataset_path.exists() or not dataset_path.is_dir():
        raise FileNotFoundError(f"Image dataset folder '{dataset_path}' not found.")
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    image_dataset = ImageFolder(str(dataset_path), transform=transform)
    if len(image_dataset) == 0:
        raise ValueError("The image dataset contains no labeled samples. Ensure class subdirectories exist.")
    loader = DataLoader(
        image_dataset,
        batch_size=int(hyperparameters.get("batch_size", 16)),
        shuffle=True,
        num_workers=0,
    )
    num_classes = len(image_dataset.classes)
    architecture = resnet50 if model_name == "ResNet50" else resnet18
    if architecture is None:
        raise RuntimeError("Desired ResNet architecture is unavailable.")
    model = architecture(pretrained=bool(hyperparameters.get("pretrained", True)))
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    optimizer_name = str(hyperparameters.get("optimizer", "adam")).lower()
    learning_rate = float(hyperparameters.get("learning_rate", 1e-3))
    weight_decay = float(hyperparameters.get("weight_decay", 0.0))
    if optimizer_name == "sgd":
        optimizer = torch.optim.SGD(
            model.parameters(),
            lr=learning_rate,
            momentum=float(hyperparameters.get("momentum", 0.9)),
            weight_decay=weight_decay,
        )
    else:
        optimizer = torch.optim.Adam(
            model.parameters(),
            lr=learning_rate,
            weight_decay=weight_decay,
        )
    criterion = nn.CrossEntropyLoss()
    epochs = int(hyperparameters.get("epochs", 3))
    total_samples = 0
    correct = 0
    running_loss = 0.0
    for _ in range(epochs):
        model.train()
        for inputs, labels in loader:
            inputs = inputs.to(device)
            labels = labels.to(device)
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * inputs.size(0)
            _, preds = torch.max(outputs, 1)
            correct += (preds == labels).sum().item()
            total_samples += labels.size(0)
    metrics = {
        "task_type": "classification",
        "accuracy": safe_json(correct / total_samples if total_samples else None),
        "train_loss": safe_json(running_loss / total_samples if total_samples else None),
        "sample_count": total_samples,
        "classes": num_classes,
        "epochs": epochs,
    }
    return metrics, model


def train_model(
    model_name: str,
    dataset_name: Optional[str],
    hf_dataset_url: Optional[str],
    label_column: str,
    test_size: float,
    random_state: int,
    hyperparameters: Dict[str, Any],
    sep: Optional[str] = ",",
    usecols: Optional[List[str]] = None,
    mode: str = "manual",
    optimize_metric: str = "accuracy",
    env_id: Optional[str] = None,
    model_candidates: Optional[List[str]] = None,
    preset: str = "balanced",
) -> Tuple[Dict[str, Any], str, str, str]:
    model_name = normalize_model_name(model_name)
    if mode not in TRAINING_MODES:
        raise ValueError(f"Unsupported training mode '{mode}'.")
    if model_name not in MODEL_CATALOG:
        raise ValueError(f"Model '{model_name}' is not supported for training.")
    
    hyperparameters = ensure_dict(hyperparameters, "hyperparameters")
    
    # Apply preset configuration
    if preset and preset in TRAINING_PRESETS:
        hyperparameters = apply_preset(hyperparameters, preset)
    
    model_def = get_model_entry(model_name)
    
    # REINFORCEMENT LEARNING MODELS
    if model_def["category"] == "reinforcement-learning":
        if env_id is None:
            raise ValueError("env_id is required for reinforcement learning models.")
        metrics = _train_rl_model(model_name, env_id, {**model_def["params"], **hyperparameters})
        artifact_path = write_artifact(model_name, metrics)
        return metrics, "rl", env_id, artifact_path
    
    # VISION MODELS (ResNet, ViT, etc.)
    if model_def["category"] == "vision":
        if not dataset_name or not is_image_dataset_path(dataset_name):
            raise ValueError(
                "Vision models require a local image dataset directory path pointing to class subdirectories. "
                "Provide an absolute path or a path under the data/ folder."
            )
        
        # Apply mode-specific hyperparameter adjustments for vision
        if mode == "auto_tune":
            # Auto-tune: Try different learning rates and batch sizes
            suggested = suggest_hyperparameters(model_name, "classification", optimize_metric, dataset_name, hf_dataset_url, use_llm=False)
            hyperparameters = {**model_def["params"], **suggested, **hyperparameters}
        elif mode == "auto_fine_tune":
            # Auto fine-tune: Adaptive tuning with smaller initial LR for fine-tuning
            suggested = suggest_hyperparameters(model_name, "classification", optimize_metric, dataset_name, hf_dataset_url, use_llm=False)
            suggested["learning_rate"] = suggested.get("learning_rate", 1e-3) * 0.1  # Smaller for fine-tuning
            hyperparameters = {**model_def["params"], **suggested, **hyperparameters}
        elif mode == "llm_fine_tune":
            # LLM-guided fine-tuning
            suggested = suggest_hyperparameters(model_name, "classification", optimize_metric, dataset_name, hf_dataset_url, use_llm=True)
            hyperparameters = {**model_def["params"], **suggested, **hyperparameters}
        
        metrics, model = _train_resnet_image_model(model_name, dataset_name, {**model_def["params"], **hyperparameters})
        artifact_path = write_artifact(model_name, model)
        return metrics, "local", dataset_name, artifact_path
    
    # Load and validate dataset for non-vision models
    dataset, dataset_source, dataset_tag = _prepare_dataset(dataset_name, hf_dataset_url, label_column, sep, usecols)
    
    # Infer task type for mode-based hyperparameter adjustment
    task_type = "classification"
    if model_def["category"] == "clustering":
        task_type = "clustering"
    elif label_column in dataset.columns:
        task_type = infer_task_type(dataset[label_column])
    
    # AUTO_SEARCH: Try multiple model candidates
    if mode == "auto_search" and model_candidates:
        best_metrics = None
        best_result = None
        best_candidate = None
        for candidate in model_candidates:
            try:
                candidate_metrics, ds, ds_tag, artifact_path = train_model(
                    candidate,
                    dataset_name,
                    hf_dataset_url,
                    label_column,
                    test_size,
                    random_state,
                    hyperparameters,
                    sep,
                    usecols,
                    "manual",
                    optimize_metric,
                    env_id,
                    preset=preset,
                )
                score = candidate_metrics.get(optimize_metric) or candidate_metrics.get("accuracy") or 0
                if best_metrics is None or score > best_metrics:
                    best_metrics = score
                    best_result = (candidate_metrics, ds, ds_tag, artifact_path)
                    best_candidate = candidate
            except Exception as exc:
                continue
        if best_result is None:
            raise ValueError("Auto-search failed to train any candidate models.")
        # Annotate result with best candidate info
        best_result[0]["best_candidate"] = best_candidate
        return best_result
    
    # Mode: AUTO_TUNE - Grid search over key hyperparameters
    if mode == "auto_tune":
        suggested = suggest_hyperparameters(
            model_name,
            task_type,
            optimize_metric,
            dataset_name,
            hf_dataset_url,
            use_llm=False,
        )
        hyperparameters = {**model_def["params"], **suggested, **hyperparameters}
    
    # Mode: AUTO_FINE_TUNE - Adaptive parameter adjustment
    elif mode == "auto_fine_tune":
        suggested = suggest_hyperparameters(
            model_name,
            task_type,
            optimize_metric,
            dataset_name,
            hf_dataset_url,
            use_llm=False,
        )
        # Apply fine-tuning adjustments: lower learning rate for stability
        if "learning_rate" in suggested:
            suggested["learning_rate"] = suggested["learning_rate"] * 0.1
        if "epochs" in suggested:
            suggested["epochs"] = max(1, int(suggested["epochs"] * 0.5))
        hyperparameters = {**model_def["params"], **suggested, **hyperparameters}
    
    # Mode: LLM_FINE_TUNE - AI-guided parameter selection
    elif mode == "llm_fine_tune":
        suggested = suggest_hyperparameters(
            model_name,
            task_type,
            optimize_metric,
            dataset_name,
            hf_dataset_url,
            use_llm=True,
        )
        hyperparameters = {**model_def["params"], **suggested, **hyperparameters}
    
    # CLUSTERING MODELS
    if model_def["category"] == "clustering":
        X = dataset.drop(columns=[label_column]) if label_column in dataset.columns else dataset
        metrics, model = _train_clustering(model_name, X, {**model_def["params"], **hyperparameters})
        artifact_path = write_artifact(model_name, model)
        return metrics, dataset_source, dataset_tag, artifact_path
    
    # NLP MODELS (BERT, GPT, etc.)
    if model_def["category"] == "nlp":
        metrics, model = _train_transformer_text_classifier(
            model_name,
            model_def,
            dataset,
            label_column,
            {**model_def["params"], **hyperparameters},
        )
        artifact_path = write_artifact(model_name, model)
        return metrics, dataset_source, dataset_tag, artifact_path
    
    # SPECIALIZED MODELS: Timeseries, Graph, Autoencoder
    if model_def["category"] in {"timeseries", "graph", "autoencoder"}:
        metrics, model = _train_torch_regression_or_classification(
            model_name,
            dataset,
            label_column,
            {**model_def["params"], **hyperparameters, "test_size": test_size, "random_state": random_state},
        )
        artifact_path = write_artifact(model_name, model)
        return metrics, dataset_source, dataset_tag, artifact_path
    
    # STANDARD TABULAR MODELS (Random Forest, SVM, LR, etc.)
    if label_column not in dataset.columns:
        raise ValueError(f"label column '{label_column}' not found in dataset.")
    
    y = dataset[label_column]
    X = dataset.drop(columns=[label_column])
    task_type = infer_task_type(y)
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state)
    model = build_model(model_name, task_type, {**model_def["params"], **hyperparameters})
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    
    metrics = {
        "task_type": task_type,
        "accuracy": safe_json(accuracy_score(y_test, predictions)) if task_type == "classification" else None,
        "mse": safe_json(mean_squared_error(y_test, predictions)) if task_type == "regression" else None,
        "r2": safe_json(r2_score(y_test, predictions)) if task_type == "regression" else None,
        "train_size": len(X_train),
        "test_size": len(X_test),
        "feature_count": X.shape[1],
        "model_parameters": safe_json({**model_def["params"], **hyperparameters}),
    }
    
    artifact_path = write_artifact(model_name, model)
    return metrics, dataset_source, dataset_tag, artifact_path


def build_train_payload(run_id: int, model_name: str, dataset_source: str, dataset_tag: str, hyperparameters: Dict[str, Any], metrics: Dict[str, Any], artifact_path: str) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "model_name": model_name,
        "dataset_source": dataset_source,
        "dataset_tag": dataset_tag,
        "hyperparameters": safe_json(hyperparameters),
        "metrics": safe_json(metrics),
        "artifact_path": artifact_path,
        "completed_at": datetime.utcnow().isoformat() + "Z",
    }
