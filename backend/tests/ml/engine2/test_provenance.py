import hashlib

from ml.engine2_train.provenance import git_commit, library_versions, sha256_file


def test_library_versions_name_every_package_that_shapes_a_result():
    versions = library_versions()

    for name in ("python", "numpy", "scipy", "scikit-learn", "xgboost", "lightgbm", "optuna",
                 "onnxruntime", "torch"):  # fmt: skip
        assert name in versions
    assert all(isinstance(v, str) and v for v in versions.values())  # "not installed" is a string


def test_the_git_commit_is_a_hash_or_none_never_an_error():
    commit = git_commit()

    assert commit is None or len(commit.split("+")[0]) == 40


def test_the_file_hash_is_the_sha256_of_its_bytes(tmp_path):
    path = tmp_path / "x"
    path.write_bytes(b"abc" * 100000)

    assert sha256_file(path) == hashlib.sha256(b"abc" * 100000).hexdigest()
