# -*- coding: utf-8 -*-

import enum
import struct
from typing import Any, Dict, List, Tuple

from qgitc.common import logger
from qgitc.models.cursor_internal.models import AvailableModel


class WireType(enum.IntEnum):
    Varint = 0
    Fixed64 = 1
    LengthDelimited = 2
    StartGroup = 3
    EndGroup = 4
    Fixed32 = 5


class AvailableModelsField(enum.IntEnum):
    Models = 2


class AvailableModelField(enum.IntEnum):
    Name = 1
    DefaultOn = 2
    LongContextOnly = 3
    ChatOnly = 4
    Agent = 5
    Thinking = 9
    DisplayName = 17
    Id = 18


class ProtobufDecoder:
    """Decodes protobuf data from Connect protocol responses."""

    @staticmethod
    def skipConnectProtocolHeader(data: bytes) -> bytes:
        """
        Skip the Connect protocol header if present.
        Connect protocol uses: 1 byte flags + 4 bytes length (big-endian)

        Args:
            data: Raw response data

        Returns:
            Protobuf message data (without header)
        """
        if len(data) < 5:
            return data

        flags = data[0]
        # Check if this looks like a Connect protocol header
        # Flags are typically 0x00 (uncompressed) or 0x01 (compressed)
        if flags in (0x00, 0x01):
            length = int.from_bytes(data[1:5], byteorder='big')
            # Sanity check: length should be reasonable
            if 0 < length <= len(data) - 5:
                return data[5: 5 + length]

        return data

    @staticmethod
    def _readVarint(data: bytes, pos: int = 0) -> Tuple[int, int]:
        """
        Read a varint from bytes.

        Args:
            data: Bytes to read from

        Returns:
            Tuple of (value, bytesRead)
        """
        result = 0
        shift = 0

        while pos < len(data):
            byte = data[pos]
            result |= (byte & 0x7f) << shift
            pos += 1

            if not (byte & 0x80):
                break

            shift += 7

        return result, pos

    @staticmethod
    def _readField(data: bytes, pos: int) -> Tuple[int, WireType, Any, int]:
        """Read a single field, return (fieldNum, wireType, value, newPosition)"""
        if pos >= len(data):
            return None, None, None, pos

        tag, pos = ProtobufDecoder._readVarint(data, pos)
        fieldNum = tag >> 3
        wireType = WireType(tag & 0x07)

        if wireType == WireType.Varint:
            value, pos = ProtobufDecoder._readVarint(data, pos)
        elif wireType == WireType.Fixed64:
            value = struct.unpack('<Q', data[pos:pos+8])[0]
            pos += 8
        elif wireType == WireType.LengthDelimited:
            length, pos = ProtobufDecoder._readVarint(data, pos)
            value = data[pos:pos+length]
            pos += length
        elif wireType == WireType.Fixed32:
            value = struct.unpack('<I', data[pos:pos+4])[0]
            pos += 4
        else:
            value = None

        return fieldNum, wireType, value, pos

    @staticmethod
    def readMessage(data: bytes) -> Dict[int, List[Tuple[WireType, Any]]]:
        """Read all fields in a message, return dict of fieldNum -> [values]"""
        fields: Dict[int, List[Tuple[WireType, Any]]] = {}
        pos = 0
        while pos < len(data):
            fieldNum, wireType, value, pos = ProtobufDecoder._readField(
                data, pos)
            if fieldNum is None:
                break
            if fieldNum not in fields:
                fields[fieldNum] = []
            fields[fieldNum].append((wireType, value))
        return fields

    @staticmethod
    def readString(data: List[Tuple[WireType, Any]]) -> str:
        if not data:
            return None

        if len(data) > 1:
            logger.warning(
                f"Expected single string field, but got {len(data)} entries")

        for wireType, value in data:
            if wireType == WireType.LengthDelimited:
                return value.decode('utf-8', errors='ignore')
            else:
                logger.warning(
                    f"Expected length-delimited wire type for string, got {wireType}")

        return None

    @staticmethod
    def readInt(data: List[Tuple[WireType, Any]]):
        if not data:
            return None

        if len(data) > 1:
            logger.warning(
                f"Expected single int field, but got {len(data)} entries")

        for wireType, value in data:
            if wireType == WireType.Varint:
                return value
            else:
                logger.warning(
                    f"Expected varint wire type for int, got {wireType}")

        return None

    @staticmethod
    def decodeModelsMessage(data: bytes) -> List[AvailableModel]:
        """ Decode a models message from Cursor API. """
        message = ProtobufDecoder.readMessage(data)
        if not message:
            logger.error("Failed to decode protobuf message: no fields found")
            return []

        models: List[AvailableModel] = []

        if AvailableModelsField.Models in message:
            for wireType, modelData in message[AvailableModelsField.Models]:
                if wireType == WireType.LengthDelimited:
                    model = ProtobufDecoder._decodeModelEntry(modelData)
                    if model:
                        models.append(model)
                else:
                    logger.warning(
                        f"Unexpected wire type for model entry: {wireType}")

        return models

    @staticmethod
    def _decodeModelEntry(data: bytes) -> AvailableModel:
        """Decode a single model entry."""
        fields = ProtobufDecoder.readMessage(data)
        if not fields:
            logger.warning("Empty model entry found in protobuf data")
            return None

        model = AvailableModel()

        if AvailableModelField.Id in fields:
            model.id = ProtobufDecoder.readString(
                fields[AvailableModelField.Id])

        if AvailableModelField.Name in fields:
            model.name = ProtobufDecoder.readString(
                fields[AvailableModelField.Name])

        if AvailableModelField.DisplayName in fields:
            model.displayName = ProtobufDecoder.readString(
                fields[AvailableModelField.DisplayName])

        if AvailableModelField.DefaultOn in fields:
            model.defaultOn = ProtobufDecoder.readInt(
                fields[AvailableModelField.DefaultOn]) == 1

        if AvailableModelField.LongContextOnly in fields:
            model.isLongContextOnly = ProtobufDecoder.readInt(
                fields[AvailableModelField.LongContextOnly]) == 1

        if AvailableModelField.ChatOnly in fields:
            model.isChatOnly = ProtobufDecoder.readInt(
                fields[AvailableModelField.ChatOnly]) == 1

        if AvailableModelField.Agent in fields:
            model.supportsAgent = ProtobufDecoder.readInt(
                fields[AvailableModelField.Agent]) == 1

        if AvailableModelField.Thinking in fields:
            model.supportsThinking = ProtobufDecoder.readInt(
                fields[AvailableModelField.Thinking]) == 1

        return model
