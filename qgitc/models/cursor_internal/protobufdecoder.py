# -*- coding: utf-8 -*-

import enum
import struct
from typing import Any, Dict, List, Tuple


class WireType(enum.IntEnum):
    Varint = 0
    Fixed64 = 1
    LengthDelimited = 2
    StartGroup = 3
    EndGroup = 4
    Fixed32 = 5


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
