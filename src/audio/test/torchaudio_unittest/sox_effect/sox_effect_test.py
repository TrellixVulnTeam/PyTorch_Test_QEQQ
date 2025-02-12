import io
import itertools
import tarfile
from pathlib import Path

from parameterized import parameterized
from torchaudio import sox_effects
from torchaudio._internal import module_utils as _mod_utils
from torchaudio_unittest.common_utils import (
    TempDirMixin,
    HttpServerMixin,
    PytorchTestCase,
    skipIfNoSox,
    skipIfNoModule,
    skipIfNoExec,
    get_asset_path,
    get_sinusoid,
    get_wav_data,
    save_wav,
    load_wav,
    sox_utils,
)

from .common import (
    load_params,
    name_func,
)


if _mod_utils.is_module_available("requests"):
    import requests


@skipIfNoSox
class TestSoxEffects(PytorchTestCase):
    def test_init(self):
        """Calling init_sox_effects multiple times does not crush"""
        for _ in range(3):
            sox_effects.init_sox_effects()


@skipIfNoSox
class TestSoxEffectsTensor(TempDirMixin, PytorchTestCase):
    """Test suite for `apply_effects_tensor` function"""

    @parameterized.expand(
        list(itertools.product(["float32", "int32", "int16", "uint8"], [8000, 16000], [1, 2, 4, 8], [True, False])),
        name_func=name_func,
    )
    def test_apply_no_effect(self, dtype, sample_rate, num_channels, channels_first):
        """`apply_effects_tensor` without effects should return identical data as input"""
        original = get_wav_data(dtype, num_channels, channels_first=channels_first)
        expected = original.clone()
        found, output_sample_rate = sox_effects.apply_effects_tensor(expected, sample_rate, [], channels_first)

        assert output_sample_rate == sample_rate
        # SoxEffect should not alter the input Tensor object
        self.assertEqual(original, expected)
        # SoxEffect should not return the same Tensor object
        assert expected is not found
        # Returned Tensor should equal to the input Tensor
        self.assertEqual(expected, found)

    @parameterized.expand(
        load_params("sox_effect_test_args.jsonl"),
        name_func=lambda f, i, p: f'{f.__name__}_{i}_{p.args[0]["effects"][0][0]}',
    )
    def test_apply_effects(self, args):
        """`apply_effects_tensor` should return identical data as sox command"""
        effects = args["effects"]
        num_channels = args.get("num_channels", 2)
        input_sr = args.get("input_sample_rate", 8000)
        output_sr = args.get("output_sample_rate")

        input_path = self.get_temp_path("input.wav")
        reference_path = self.get_temp_path("reference.wav")

        original = get_sinusoid(frequency=800, sample_rate=input_sr, n_channels=num_channels, dtype="float32")
        save_wav(input_path, original, input_sr)
        sox_utils.run_sox_effect(input_path, reference_path, effects, output_sample_rate=output_sr)

        expected, expected_sr = load_wav(reference_path)
        found, sr = sox_effects.apply_effects_tensor(original, input_sr, effects)

        assert sr == expected_sr
        self.assertEqual(expected, found)


@skipIfNoSox
class TestSoxEffectsFile(TempDirMixin, PytorchTestCase):
    """Test suite for `apply_effects_file` function"""

    @parameterized.expand(
        list(
            itertools.product(
                ["float32", "int32", "int16", "uint8"],
                [8000, 16000],
                [1, 2, 4, 8],
                [False, True],
            )
        ),
        name_func=name_func,
    )
    def test_apply_no_effect(self, dtype, sample_rate, num_channels, channels_first):
        """`apply_effects_file` without effects should return identical data as input"""
        path = self.get_temp_path("input.wav")
        expected = get_wav_data(dtype, num_channels, channels_first=channels_first)
        save_wav(path, expected, sample_rate, channels_first=channels_first)

        found, output_sample_rate = sox_effects.apply_effects_file(
            path, [], normalize=False, channels_first=channels_first
        )

        assert output_sample_rate == sample_rate
        self.assertEqual(expected, found)

    @parameterized.expand(
        load_params("sox_effect_test_args.jsonl"),
        name_func=lambda f, i, p: f'{f.__name__}_{i}_{p.args[0]["effects"][0][0]}',
    )
    def test_apply_effects_str(self, args):
        """`apply_effects_file` should return identical data as sox command"""
        dtype = "int32"
        channels_first = True
        effects = args["effects"]
        num_channels = args.get("num_channels", 2)
        input_sr = args.get("input_sample_rate", 8000)
        output_sr = args.get("output_sample_rate")

        input_path = self.get_temp_path("input.wav")
        reference_path = self.get_temp_path("reference.wav")
        data = get_wav_data(dtype, num_channels, channels_first=channels_first)
        save_wav(input_path, data, input_sr, channels_first=channels_first)
        sox_utils.run_sox_effect(input_path, reference_path, effects, output_sample_rate=output_sr)

        expected, expected_sr = load_wav(reference_path)
        found, sr = sox_effects.apply_effects_file(input_path, effects, normalize=False, channels_first=channels_first)

        assert sr == expected_sr
        self.assertEqual(found, expected)

    def test_apply_effects_path(self):
        """`apply_effects_file` should return identical data as sox command when file path is given as a Path Object"""
        dtype = "int32"
        channels_first = True
        effects = [["hilbert"]]
        num_channels = 2
        input_sr = 8000
        output_sr = 8000

        input_path = self.get_temp_path("input.wav")
        reference_path = self.get_temp_path("reference.wav")
        data = get_wav_data(dtype, num_channels, channels_first=channels_first)
        save_wav(input_path, data, input_sr, channels_first=channels_first)
        sox_utils.run_sox_effect(input_path, reference_path, effects, output_sample_rate=output_sr)

        expected, expected_sr = load_wav(reference_path)
        found, sr = sox_effects.apply_effects_file(
            Path(input_path), effects, normalize=False, channels_first=channels_first
        )

        assert sr == expected_sr
        self.assertEqual(found, expected)


@skipIfNoSox
class TestFileFormats(TempDirMixin, PytorchTestCase):
    """`apply_effects_file` gives the same result as sox on various file formats"""

    @parameterized.expand(
        list(
            itertools.product(
                ["float32", "int32", "int16", "uint8"],
                [8000, 16000],
                [1, 2],
            )
        ),
        name_func=lambda f, _, p: f'{f.__name__}_{"_".join(str(arg) for arg in p.args)}',
    )
    def test_wav(self, dtype, sample_rate, num_channels):
        """`apply_effects_file` works on various wav format"""
        channels_first = True
        effects = [["band", "300", "10"]]

        input_path = self.get_temp_path("input.wav")
        reference_path = self.get_temp_path("reference.wav")
        data = get_wav_data(dtype, num_channels, channels_first=channels_first)
        save_wav(input_path, data, sample_rate, channels_first=channels_first)
        sox_utils.run_sox_effect(input_path, reference_path, effects)

        expected, expected_sr = load_wav(reference_path)
        found, sr = sox_effects.apply_effects_file(input_path, effects, normalize=False, channels_first=channels_first)

        assert sr == expected_sr
        self.assertEqual(found, expected)

    @parameterized.expand(
        list(
            itertools.product(
                [8000, 16000],
                [1, 2],
            )
        ),
        name_func=lambda f, _, p: f'{f.__name__}_{"_".join(str(arg) for arg in p.args)}',
    )
    def test_mp3(self, sample_rate, num_channels):
        """`apply_effects_file` works on various mp3 format"""
        channels_first = True
        effects = [["band", "300", "10"]]

        input_path = self.get_temp_path("input.mp3")
        reference_path = self.get_temp_path("reference.wav")
        sox_utils.gen_audio_file(input_path, sample_rate, num_channels)
        sox_utils.run_sox_effect(input_path, reference_path, effects)

        expected, expected_sr = load_wav(reference_path)
        found, sr = sox_effects.apply_effects_file(input_path, effects, channels_first=channels_first)
        save_wav(self.get_temp_path("result.wav"), found, sr, channels_first=channels_first)

        assert sr == expected_sr
        self.assertEqual(found, expected, atol=1e-4, rtol=1e-8)

    @parameterized.expand(
        list(
            itertools.product(
                [8000, 16000],
                [1, 2],
            )
        ),
        name_func=lambda f, _, p: f'{f.__name__}_{"_".join(str(arg) for arg in p.args)}',
    )
    def test_flac(self, sample_rate, num_channels):
        """`apply_effects_file` works on various flac format"""
        channels_first = True
        effects = [["band", "300", "10"]]

        input_path = self.get_temp_path("input.flac")
        reference_path = self.get_temp_path("reference.wav")
        sox_utils.gen_audio_file(input_path, sample_rate, num_channels)
        sox_utils.run_sox_effect(input_path, reference_path, effects, output_bitdepth=32)

        expected, expected_sr = load_wav(reference_path)
        found, sr = sox_effects.apply_effects_file(input_path, effects, channels_first=channels_first)
        save_wav(self.get_temp_path("result.wav"), found, sr, channels_first=channels_first)

        assert sr == expected_sr
        self.assertEqual(found, expected)

    @parameterized.expand(
        list(
            itertools.product(
                [8000, 16000],
                [1, 2],
            )
        ),
        name_func=lambda f, _, p: f'{f.__name__}_{"_".join(str(arg) for arg in p.args)}',
    )
    def test_vorbis(self, sample_rate, num_channels):
        """`apply_effects_file` works on various vorbis format"""
        channels_first = True
        effects = [["band", "300", "10"]]

        input_path = self.get_temp_path("input.vorbis")
        reference_path = self.get_temp_path("reference.wav")
        sox_utils.gen_audio_file(input_path, sample_rate, num_channels)
        sox_utils.run_sox_effect(input_path, reference_path, effects, output_bitdepth=32)

        expected, expected_sr = load_wav(reference_path)
        found, sr = sox_effects.apply_effects_file(input_path, effects, channels_first=channels_first)
        save_wav(self.get_temp_path("result.wav"), found, sr, channels_first=channels_first)

        assert sr == expected_sr
        self.assertEqual(found, expected)


@skipIfNoSox
class TestApplyEffectFileWithoutExtension(PytorchTestCase):
    def test_mp3(self):
        """Providing format allows to read mp3 without extension

        libsox does not check header for mp3

        https://github.com/pytorch/audio/issues/1040

        The file was generated with the following command
            ffmpeg -f lavfi -i "sine=frequency=1000:duration=5" -ar 16000 -f mp3 test_noext
        """
        effects = [["band", "300", "10"]]
        path = get_asset_path("mp3_without_ext")
        _, sr = sox_effects.apply_effects_file(path, effects, format="mp3")
        assert sr == 16000


@skipIfNoExec("sox")
@skipIfNoSox
class TestFileObject(TempDirMixin, PytorchTestCase):
    @parameterized.expand(
        [
            ("wav", None),
            ("mp3", 128),
            ("mp3", 320),
            ("flac", 0),
            ("flac", 5),
            ("flac", 8),
            ("vorbis", -1),
            ("vorbis", 10),
            ("amb", None),
        ]
    )
    def test_fileobj(self, ext, compression):
        """Applying effects via file object works"""
        sample_rate = 16000
        channels_first = True
        effects = [["band", "300", "10"]]
        format_ = ext if ext in ["mp3"] else None
        input_path = self.get_temp_path(f"input.{ext}")
        reference_path = self.get_temp_path("reference.wav")

        sox_utils.gen_audio_file(input_path, sample_rate, num_channels=2, compression=compression)
        sox_utils.run_sox_effect(input_path, reference_path, effects, output_bitdepth=32)
        expected, expected_sr = load_wav(reference_path)

        with open(input_path, "rb") as fileobj:
            found, sr = sox_effects.apply_effects_file(fileobj, effects, channels_first=channels_first, format=format_)
        save_wav(self.get_temp_path("result.wav"), found, sr, channels_first=channels_first)
        assert sr == expected_sr
        self.assertEqual(found, expected)

    @parameterized.expand(
        [
            ("wav", None),
            ("mp3", 128),
            ("mp3", 320),
            ("flac", 0),
            ("flac", 5),
            ("flac", 8),
            ("vorbis", -1),
            ("vorbis", 10),
            ("amb", None),
        ]
    )
    def test_bytesio(self, ext, compression):
        """Applying effects via BytesIO object works"""
        sample_rate = 16000
        channels_first = True
        effects = [["band", "300", "10"]]
        format_ = ext if ext in ["mp3"] else None
        input_path = self.get_temp_path(f"input.{ext}")
        reference_path = self.get_temp_path("reference.wav")

        sox_utils.gen_audio_file(input_path, sample_rate, num_channels=2, compression=compression)
        sox_utils.run_sox_effect(input_path, reference_path, effects, output_bitdepth=32)
        expected, expected_sr = load_wav(reference_path)

        with open(input_path, "rb") as file_:
            fileobj = io.BytesIO(file_.read())
        found, sr = sox_effects.apply_effects_file(fileobj, effects, channels_first=channels_first, format=format_)
        save_wav(self.get_temp_path("result.wav"), found, sr, channels_first=channels_first)
        assert sr == expected_sr
        self.assertEqual(found, expected)

    @parameterized.expand(
        [
            ("wav", None),
            ("mp3", 128),
            ("mp3", 320),
            ("flac", 0),
            ("flac", 5),
            ("flac", 8),
            ("vorbis", -1),
            ("vorbis", 10),
            ("amb", None),
        ]
    )
    def test_tarfile(self, ext, compression):
        """Applying effects to compressed audio via file-like file works"""
        sample_rate = 16000
        channels_first = True
        effects = [["band", "300", "10"]]
        format_ = ext if ext in ["mp3"] else None
        audio_file = f"input.{ext}"

        input_path = self.get_temp_path(audio_file)
        reference_path = self.get_temp_path("reference.wav")
        archive_path = self.get_temp_path("archive.tar.gz")

        sox_utils.gen_audio_file(input_path, sample_rate, num_channels=2, compression=compression)
        sox_utils.run_sox_effect(input_path, reference_path, effects, output_bitdepth=32)
        expected, expected_sr = load_wav(reference_path)

        with tarfile.TarFile(archive_path, "w") as tarobj:
            tarobj.add(input_path, arcname=audio_file)
        with tarfile.TarFile(archive_path, "r") as tarobj:
            fileobj = tarobj.extractfile(audio_file)
            found, sr = sox_effects.apply_effects_file(fileobj, effects, channels_first=channels_first, format=format_)
        save_wav(self.get_temp_path("result.wav"), found, sr, channels_first=channels_first)
        assert sr == expected_sr
        self.assertEqual(found, expected)


@skipIfNoSox
@skipIfNoExec("sox")
@skipIfNoModule("requests")
class TestFileObjectHttp(HttpServerMixin, PytorchTestCase):
    @parameterized.expand(
        [
            ("wav", None),
            ("mp3", 128),
            ("mp3", 320),
            ("flac", 0),
            ("flac", 5),
            ("flac", 8),
            ("vorbis", -1),
            ("vorbis", 10),
            ("amb", None),
        ]
    )
    def test_requests(self, ext, compression):
        sample_rate = 16000
        channels_first = True
        effects = [["band", "300", "10"]]
        format_ = ext if ext in ["mp3"] else None
        audio_file = f"input.{ext}"
        input_path = self.get_temp_path(audio_file)
        reference_path = self.get_temp_path("reference.wav")

        sox_utils.gen_audio_file(input_path, sample_rate, num_channels=2, compression=compression)
        sox_utils.run_sox_effect(input_path, reference_path, effects, output_bitdepth=32)
        expected, expected_sr = load_wav(reference_path)

        url = self.get_url(audio_file)
        with requests.get(url, stream=True) as resp:
            found, sr = sox_effects.apply_effects_file(resp.raw, effects, channels_first=channels_first, format=format_)
        save_wav(self.get_temp_path("result.wav"), found, sr, channels_first=channels_first)
        assert sr == expected_sr
        self.assertEqual(found, expected)
