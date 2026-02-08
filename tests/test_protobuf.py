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

        message = ProtobufDecoder.readMessage(decompressed)
        self.assertIsNotNone(message)

        #TODO: decode
