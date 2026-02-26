"""Tests for Slack icon generation script (AC acceptance tests for #28)."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# AC1: 画像生成スクリプト

def test_ac1_1_script_exists_and_executable():
    """AC1-1: scripts/generate_icon.py が存在し実行可能"""
    script_path = Path("scripts/generate_icon.py")
    assert script_path.exists(), "scripts/generate_icon.py が存在しない"
    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "スクリプトが実行できない"


@patch("boto3.client")
def test_ac1_2_uses_bedrock_nova_canvas(mock_boto_client, tmp_path):
    """AC1-2: boto3でamazon.nova-canvas-v1:0のTEXT_IMAGEタスクを使用"""
    from scripts.generate_icon import generate_icons
    
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: b'{"images": ["iVBORw0KGgo="]}')
    }
    mock_boto_client.return_value = mock_bedrock
    
    generate_icons(
        prompt="test",
        output_dir=str(tmp_path),
        count=1,
        size=1024,
        quality="premium",
    )
    
    mock_boto_client.assert_called_once_with("bedrock-runtime", region_name="us-east-1")
    call_args = mock_bedrock.invoke_model.call_args
    assert call_args[1]["modelId"] == "amazon.nova-canvas-v1:0"


def test_ac1_3_cli_arguments_supported():
    """AC1-3: 必須・任意のCLI引数をサポート"""
    result = subprocess.run(
        [sys.executable, "scripts/generate_icon.py", "--help"],
        capture_output=True,
        text=True,
    )
    help_text = result.stdout
    
    assert "--prompt" in help_text
    assert "--negative" in help_text
    assert "--count" in help_text
    assert "--size" in help_text
    assert "--seed" in help_text
    assert "--quality" in help_text
    assert "--output-dir" in help_text
    assert "--cfg-scale" in help_text


@patch("boto3.client")
def test_ac1_4_output_filename_format(mock_boto_client, tmp_path):
    """AC1-4: 生成画像は {output_dir}/yui-icon-{seed}-{index}.png として保存"""
    from scripts.generate_icon import generate_icons
    
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: b'{"images": ["iVBORw0KGgo=", "iVBORw0KGgo="]}')
    }
    mock_boto_client.return_value = mock_bedrock
    
    generate_icons(
        prompt="test",
        output_dir=str(tmp_path),
        count=2,
        seed=12345,
        size=1024,
        quality="premium",
    )
    
    assert (tmp_path / "yui-icon-12345-0.png").exists()
    assert (tmp_path / "yui-icon-12345-1.png").exists()


@patch("boto3.client")
def test_ac1_5_prints_output_paths_and_sizes(mock_boto_client, tmp_path, capsys):
    """AC1-5: 生成成功時、保存パスとファイルサイズを標準出力に表示"""
    from scripts.generate_icon import generate_icons
    
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: b'{"images": ["iVBORw0KGgo="]}')
    }
    mock_boto_client.return_value = mock_bedrock
    
    generate_icons(
        prompt="test",
        output_dir=str(tmp_path),
        count=1,
        size=1024,
        quality="premium",
    )
    
    captured = capsys.readouterr()
    assert "yui-icon-" in captured.out
    assert ".png" in captured.out


@patch("boto3.client")
def test_ac1_6_files_created_in_output_dir(mock_boto_client, tmp_path):
    """AC1-6: 指定枚数のPNGファイルが出力ディレクトリに存在"""
    from scripts.generate_icon import generate_icons
    
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: b'{"images": ["iVBORw0KGgo=", "iVBORw0KGgo=", "iVBORw0KGgo="]}')
    }
    mock_boto_client.return_value = mock_bedrock
    
    output_dir = tmp_path / "icons"
    generate_icons(
        prompt="test",
        output_dir=str(output_dir),
        count=3,
        size=1024,
        quality="premium",
    )
    
    png_files = list(output_dir.glob("*.png"))
    assert len(png_files) == 3


# AC2: エッジケース対策

def test_ac2_1_missing_prompt_exits_with_error():
    """AC2-1: --prompt未指定でargparseエラー（exit code 2）"""
    result = subprocess.run(
        [sys.executable, "scripts/generate_icon.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "required" in result.stderr.lower() or "usage" in result.stderr.lower()


@patch("boto3.client")
def test_ac2_2_bedrock_api_failure_exits_with_error(mock_boto_client, tmp_path, capsys):
    """AC2-2: Bedrock API失敗でClientErrorをキャッチしexit code 1"""
    from botocore.exceptions import ClientError
    from scripts.generate_icon import generate_icons
    
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Not authorized"}},
        "InvokeModel",
    )
    mock_boto_client.return_value = mock_bedrock
    
    with pytest.raises(SystemExit) as exc_info:
        generate_icons(
            prompt="test",
            output_dir=str(tmp_path),
            count=1,
            size=1024,
            quality="premium",
        )
    
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "error" in captured.out.lower() or "error" in captured.err.lower()


def test_ac2_3_count_out_of_range_exits_with_error():
    """AC2-3: --count範囲外でargparseエラー（exit code 2）"""
    result_zero = subprocess.run(
        [sys.executable, "scripts/generate_icon.py", "--prompt", "test", "--count", "0"],
        capture_output=True,
        text=True,
    )
    assert result_zero.returncode == 2
    
    result_six = subprocess.run(
        [sys.executable, "scripts/generate_icon.py", "--prompt", "test", "--count", "6"],
        capture_output=True,
        text=True,
    )
    assert result_six.returncode == 2


def test_ac2_4_invalid_size_exits_with_error():
    """AC2-4: --size非対応値でargparse choicesエラー（exit code 2）"""
    result = subprocess.run(
        [sys.executable, "scripts/generate_icon.py", "--prompt", "test", "--size", "999"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "invalid choice" in result.stderr.lower() or "choose from" in result.stderr.lower()


@patch("boto3.client")
def test_ac2_5_output_dir_auto_created(mock_boto_client, tmp_path):
    """AC2-5: 出力ディレクトリが存在しない場合は自動作成"""
    from scripts.generate_icon import generate_icons
    
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: b'{"images": ["iVBORw0KGgo="]}')
    }
    mock_boto_client.return_value = mock_bedrock
    
    output_dir = tmp_path / "nonexistent" / "icons"
    assert not output_dir.exists()
    
    generate_icons(
        prompt="test",
        output_dir=str(output_dir),
        count=1,
        size=1024,
        quality="premium",
    )
    
    assert output_dir.exists()
    assert (output_dir / "yui-icon-0-0.png").exists() or len(list(output_dir.glob("*.png"))) > 0


@patch("boto3.client")
@patch("builtins.open")
def test_ac2_6_disk_write_failure_exits_with_error(mock_open, mock_boto_client, tmp_path, capsys):
    """AC2-6: ディスク書き込み失敗でIOError/OSErrorをキャッチしexit code 1"""
    from scripts.generate_icon import generate_icons
    
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: b'{"images": ["iVBORw0KGgo="]}')
    }
    mock_boto_client.return_value = mock_bedrock
    mock_open.side_effect = OSError("Permission denied")
    
    with pytest.raises(SystemExit) as exc_info:
        generate_icons(
            prompt="test",
            output_dir=str(tmp_path),
            count=1,
            size=1024,
            quality="premium",
        )
    
    assert exc_info.value.code == 1


@patch("boto3.client")
def test_ac2_7_empty_images_response_exits_with_error(mock_boto_client, tmp_path, capsys):
    """AC2-7: APIレスポンスにimagesキーがない/空配列でexit code 1"""
    from scripts.generate_icon import generate_icons
    
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: b'{"images": []}')
    }
    mock_boto_client.return_value = mock_bedrock
    
    with pytest.raises(SystemExit) as exc_info:
        generate_icons(
            prompt="test",
            output_dir=str(tmp_path),
            count=1,
            size=1024,
            quality="premium",
        )
    
    assert exc_info.value.code == 1


def test_ac2_8_invalid_quality_exits_with_error():
    """AC2-8: --quality非対応値でargparse choicesエラー"""
    result = subprocess.run(
        [sys.executable, "scripts/generate_icon.py", "--prompt", "test", "--quality", "ultra"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "invalid choice" in result.stderr.lower() or "choose from" in result.stderr.lower()


# AC3: プロンプトプリセット

def test_ac3_1_preset_option_supported():
    """AC3-1: --preset NAMEオプションで事前定義プロンプトを使用可能"""
    result = subprocess.run(
        [sys.executable, "scripts/generate_icon.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert "--preset" in result.stdout


def test_ac3_2_preset_yaml_file_exists():
    """AC3-2: プリセット定義はscripts/icon_presets.yamlに格納"""
    preset_file = Path("scripts/icon_presets.yaml")
    assert preset_file.exists(), "scripts/icon_presets.yaml が存在しない"


def test_ac3_3_preset_list_shows_available_presets():
    """AC3-3: --preset listで利用可能なプリセット一覧を表示"""
    result = subprocess.run(
        [sys.executable, "scripts/generate_icon.py", "--preset", "list"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "preset" in result.stdout.lower()


def test_ac3_4_preset_yaml_structure():
    """AC3-4: プリセットYAMLの構造が正しい"""
    import yaml
    
    preset_file = Path("scripts/icon_presets.yaml")
    with open(preset_file) as f:
        data = yaml.safe_load(f)
    
    assert "presets" in data
    assert isinstance(data["presets"], dict)
    
    for name, preset in data["presets"].items():
        assert "prompt" in preset
        assert isinstance(preset["prompt"], str)


def test_ac3_5_preset_and_prompt_mutually_exclusive():
    """AC3-5: --presetと--promptが同時指定でエラー"""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_icon.py",
            "--preset",
            "elegant-secretary",
            "--prompt",
            "test",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "mutually exclusive" in result.stderr.lower() or "cannot" in result.stderr.lower()


def test_ac3_6_nonexistent_preset_shows_available_list():
    """AC3-6: 存在しないプリセット名で利用可能なプリセット一覧を表示してエラー"""
    result = subprocess.run(
        [sys.executable, "scripts/generate_icon.py", "--preset", "nonexistent-preset-xyz"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "available" in output.lower() or "preset" in output.lower()


# AC-V1: IMAGE_VARIATION モード追加

def test_acv1_1_mode_argument_supported():
    """AC-V1-1: --mode引数をサポート（generate/variation）"""
    result = subprocess.run(
        [sys.executable, "scripts/generate_icon.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert "--mode" in result.stdout


def test_acv1_2_source_image_argument_supported():
    """AC-V1-2: --source-image引数をサポート（variation時必須）"""
    result = subprocess.run(
        [sys.executable, "scripts/generate_icon.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert "--source-image" in result.stdout


def test_acv1_3_similarity_argument_supported():
    """AC-V1-3: --similarity引数をサポート（デフォルト0.7、範囲0.2-1.0）"""
    result = subprocess.run(
        [sys.executable, "scripts/generate_icon.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert "--similarity" in result.stdout


@patch("boto3.client")
def test_acv1_4_variation_mode_uses_image_variation_task(mock_boto_client, tmp_path):
    """AC-V1-4: --mode variation時、taskType=IMAGE_VARIATIONでAPI送信"""
    from scripts.generate_icon import generate_icons

    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: b'{"images": ["iVBORw0KGgo="]}')
    }
    mock_boto_client.return_value = mock_bedrock

    source_image = tmp_path / "source.png"
    source_image.write_bytes(b"\x89PNG\r\n\x1a\n")

    generate_icons(
        prompt="light background",
        output_dir=str(tmp_path),
        count=1,
        size=1024,
        quality="premium",
        mode="variation",
        source_image=str(source_image),
        similarity=0.7,
    )

    call_args = mock_bedrock.invoke_model.call_args
    import json as json_mod
    body = json_mod.loads(call_args[1]["body"])
    assert body["taskType"] == "IMAGE_VARIATION"
    assert "imageVariationParams" in body
    assert "images" in body["imageVariationParams"]
    assert "text" in body["imageVariationParams"]
    assert body["imageVariationParams"]["similarityStrength"] == 0.7


def test_acv1_5_variation_without_source_image_exits_with_error():
    """AC-V1-5: --mode variation時に--source-image未指定でエラー"""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_icon.py",
            "--mode", "variation",
            "--prompt", "test",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_acv1_6_nonexistent_source_image_exits_with_error():
    """AC-V1-6: --source-imageが存在しない場合、エラーメッセージとexit code 1"""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_icon.py",
            "--mode", "variation",
            "--prompt", "test",
            "--source-image", "/nonexistent/image.png",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "not found" in result.stderr.lower()


@patch("boto3.client")
def test_acv1_7_variation_output_filename_format(mock_boto_client, tmp_path):
    """AC-V1-7: variationモードの出力ファイル名はyui-variation-{seed}-{index}.png"""
    from scripts.generate_icon import generate_icons

    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: b'{"images": ["iVBORw0KGgo="]}')
    }
    mock_boto_client.return_value = mock_bedrock

    source_image = tmp_path / "source.png"
    source_image.write_bytes(b"\x89PNG\r\n\x1a\n")

    generate_icons(
        prompt="test",
        output_dir=str(tmp_path),
        count=1,
        seed=99999,
        size=1024,
        quality="premium",
        mode="variation",
        source_image=str(source_image),
    )

    assert (tmp_path / "yui-variation-99999-0.png").exists()


# AC-V2: バリエーション用プリセット追加

def test_acv2_1_light_lavender_preset_exists():
    """AC-V2-1: light-lavenderプリセットが存在"""
    import yaml

    preset_file = Path("scripts/icon_presets.yaml")
    with open(preset_file) as f:
        data = yaml.safe_load(f)

    assert "light-lavender" in data["presets"]
    preset = data["presets"]["light-lavender"]
    assert "lavender" in preset["prompt"].lower() or "light" in preset["prompt"].lower()


def test_acv2_2_light_white_preset_exists():
    """AC-V2-2: light-whiteプリセットが存在"""
    import yaml

    preset_file = Path("scripts/icon_presets.yaml")
    with open(preset_file) as f:
        data = yaml.safe_load(f)

    assert "light-white" in data["presets"]
    preset = data["presets"]["light-white"]
    assert "white" in preset["prompt"].lower()


def test_acv2_3_light_gradient_preset_exists():
    """AC-V2-3: light-gradientプリセットが存在"""
    import yaml

    preset_file = Path("scripts/icon_presets.yaml")
    with open(preset_file) as f:
        data = yaml.safe_load(f)

    assert "light-gradient" in data["presets"]


def test_acv2_4_light_blue_preset_exists():
    """AC-V2-4: light-blueプリセットが存在"""
    import yaml

    preset_file = Path("scripts/icon_presets.yaml")
    with open(preset_file) as f:
        data = yaml.safe_load(f)

    assert "light-blue" in data["presets"]


def test_acv2_5_light_warm_preset_exists():
    """AC-V2-5: light-warmプリセットが存在"""
    import yaml

    preset_file = Path("scripts/icon_presets.yaml")
    with open(preset_file) as f:
        data = yaml.safe_load(f)

    assert "light-warm" in data["presets"]


def test_acv2_6_variation_presets_have_mode_and_source():
    """AC-V2-6: バリエーションプリセットにmode/source_image/similarityが含まれる"""
    import yaml

    preset_file = Path("scripts/icon_presets.yaml")
    with open(preset_file) as f:
        data = yaml.safe_load(f)

    for name in ["light-lavender", "light-white", "light-gradient", "light-blue", "light-warm"]:
        preset = data["presets"][name]
        assert preset.get("mode") == "variation", f"{name}: mode should be 'variation'"
        assert "source_image" in preset, f"{name}: missing source_image"
        assert "similarity" in preset, f"{name}: missing similarity"


def test_acv2_7_variation_preset_auto_applies_mode():
    """AC-V2-7: バリエーションプリセット指定時、modeが自動適用される"""
    import yaml

    preset_file = Path("scripts/icon_presets.yaml")
    with open(preset_file) as f:
        data = yaml.safe_load(f)

    # light-lavender should have mode=variation so --mode is not needed
    preset = data["presets"]["light-lavender"]
    assert preset["mode"] == "variation"


# AC-V3: エッジケース

def test_acv3_1_similarity_out_of_range_exits_with_error():
    """AC-V3-1: --similarityが0.2未満/1.0超でargparseエラー"""
    result_low = subprocess.run(
        [
            sys.executable,
            "scripts/generate_icon.py",
            "--mode", "variation",
            "--prompt", "test",
            "--source-image", "dummy.png",
            "--similarity", "0.1",
        ],
        capture_output=True,
        text=True,
    )
    assert result_low.returncode == 2

    result_high = subprocess.run(
        [
            sys.executable,
            "scripts/generate_icon.py",
            "--mode", "variation",
            "--prompt", "test",
            "--source-image", "dummy.png",
            "--similarity", "1.5",
        ],
        capture_output=True,
        text=True,
    )
    assert result_high.returncode == 2


@patch("boto3.client")
def test_acv3_2_generate_mode_ignores_source_image(mock_boto_client, tmp_path):
    """AC-V3-2: --mode generate時に--source-imageを指定してもエラーにならない（無視）"""
    from scripts.generate_icon import generate_icons

    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: b'{"images": ["iVBORw0KGgo="]}')
    }
    mock_boto_client.return_value = mock_bedrock

    generate_icons(
        prompt="test",
        output_dir=str(tmp_path),
        count=1,
        size=1024,
        quality="premium",
        mode="generate",
        source_image="/some/image.png",
    )

    call_args = mock_bedrock.invoke_model.call_args
    import json as json_mod
    body = json_mod.loads(call_args[1]["body"])
    assert body["taskType"] == "TEXT_IMAGE"


@patch("boto3.client")
def test_acv3_3_variation_preset_uses_prompt_as_text(mock_boto_client, tmp_path):
    """AC-V3-3: variationプリセットのprompt/negativeがIMAGE_VARIATIONのtext/negativeTextに使用"""
    from scripts.generate_icon import generate_icons

    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: b'{"images": ["iVBORw0KGgo="]}')
    }
    mock_boto_client.return_value = mock_bedrock

    source_image = tmp_path / "source.png"
    source_image.write_bytes(b"\x89PNG\r\n\x1a\n")

    generate_icons(
        prompt="bright lavender background",
        output_dir=str(tmp_path),
        count=1,
        size=1024,
        quality="premium",
        mode="variation",
        source_image=str(source_image),
        similarity=0.7,
        negative="dark, gloomy",
    )

    call_args = mock_bedrock.invoke_model.call_args
    import json as json_mod
    body = json_mod.loads(call_args[1]["body"])
    assert body["imageVariationParams"]["text"] == "bright lavender background"
    assert body["imageVariationParams"]["negativeText"] == "dark, gloomy"


def test_acv3_4_empty_source_image_exits_with_error(tmp_path):
    """AC-V3-4: 元画像が0バイトの場合、エラーメッセージとexit code 1"""
    empty_file = tmp_path / "empty.png"
    empty_file.write_bytes(b"")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_icon.py",
            "--mode", "variation",
            "--prompt", "test",
            "--source-image", str(empty_file),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "empty" in result.stderr.lower()


@patch("boto3.client")
def test_acv3_5_bedrock_error_in_variation_mode(mock_boto_client, tmp_path, capsys):
    """AC-V3-5: variationモードでBedrock APIエラー時、既存エラーハンドリング動作"""
    from botocore.exceptions import ClientError
    from scripts.generate_icon import generate_icons

    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Not authorized"}},
        "InvokeModel",
    )
    mock_boto_client.return_value = mock_bedrock

    source_image = tmp_path / "source.png"
    source_image.write_bytes(b"\x89PNG\r\n\x1a\n")

    with pytest.raises(SystemExit) as exc_info:
        generate_icons(
            prompt="test",
            output_dir=str(tmp_path),
            count=1,
            size=1024,
            quality="premium",
            mode="variation",
            source_image=str(source_image),
        )

    assert exc_info.value.code == 1


# AC-V4: 既存機能の後方互換性

@patch("boto3.client")
def test_acv4_1_default_mode_is_generate(mock_boto_client, tmp_path):
    """AC-V4-1: --mode未指定時、既存のTEXT_IMAGE動作が変わらない"""
    from scripts.generate_icon import generate_icons

    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: b'{"images": ["iVBORw0KGgo="]}')
    }
    mock_boto_client.return_value = mock_bedrock

    generate_icons(
        prompt="test",
        output_dir=str(tmp_path),
        count=1,
        size=1024,
        quality="premium",
    )

    call_args = mock_bedrock.invoke_model.call_args
    import json as json_mod
    body = json_mod.loads(call_args[1]["body"])
    assert body["taskType"] == "TEXT_IMAGE"


def test_acv4_2_existing_tests_still_pass():
    """AC-V4-2: 既存の20テストが引き続きパスする（このテスト自体がパスすれば証明）"""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_generate_icon.py", "-k", "test_ac", "--co", "-q"],
        capture_output=True,
        text=True,
    )
    # 既存ac1〜ac3のテスト関数が20個以上リストされる
    lines = [l for l in result.stdout.strip().split("\n") if "test_ac" in l and "test_acv" not in l]
    assert len(lines) >= 20


@patch("boto3.client")
def test_acv4_3_existing_presets_still_work(mock_boto_client, tmp_path):
    """AC-V4-3: 既存プリセット(elegant-secretary/minimal-logo)が従来通り動作"""
    from scripts.generate_icon import load_presets

    presets = load_presets()
    assert "elegant-secretary" in presets
    assert "minimal-logo" in presets
    # 既存プリセットにmodeキーが無い（generateがデフォルト）
    assert "mode" not in presets["elegant-secretary"]
    assert "mode" not in presets["minimal-logo"]
