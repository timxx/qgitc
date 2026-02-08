import os
import unittest

from qgitc.models.cursor_internal.protobufdecoder import ProtobufDecoder
from qgitc.models.cursor_internal.utils import decompressGzip
from tests.base import getDataFilePath


class TestProtobufDecoder(unittest.TestCase):

    def test_decodeModels(self):
        dataFile = getDataFilePath("models.bin")
        self.assertTrue(os.path.exists(dataFile),
                        f"Test data file not found: {dataFile}")

        with open(dataFile, "rb") as f:
            data = f.read()

        decompressed = decompressGzip(data)
        self.assertIsNotNone(decompressed)

        result = ProtobufDecoder.decodeModelsMessage(decompressed)
        self.assertIsNotNone(result)

        self.assertEqual(len(result), 52)

        totalDefaultOn = sum(1 for model in result if model.defaultOn)
        self.assertEqual(totalDefaultOn, 7)

        self.assertEqual(result[0].id, "default")
