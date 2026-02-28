#!/usr/bin/env python3
"""
Kika — CLI and dashboard for Therminos on-chain temperature checker (crypto price and volatility).
Read heat bands, report prices as updater, export history. Single-file app.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
APP_NAME = "Kika"
VERSION = "1.0.0"
CONFIG_FILENAME = "kika_config.json"
DEFAULT_RPC = "https://eth.llamarpc.com"
BAND_NAMES = ("cold", "mild", "warm", "hot", "critical")
BAND_COLD, BAND_MILD, BAND_WARM, BAND_HOT, BAND_CRITICAL = 0, 1, 2, 3, 4
E8 = 10**8
BPS_BASE = 10_000

# Minimal ABI for Therminos (view + reportPrice + batchReportPrices + config)
THRMINOS_ABI = [
    {"inputs": [], "name": "getRegisteredSymbols", "outputs": [{"internalType": "bytes32[]", "name": "", "type": "bytes32[]"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getHeatSummary", "outputs": [
        {"internalType": "bytes32[]", "name": "symbolHashes", "type": "bytes32[]"},
        {"internalType": "uint8[]", "name": "bands", "type": "uint8[]"},
        {"internalType": "uint256[]", "name": "volatilitiesE8", "type": "uint256[]"},
        {"internalType": "uint256[]", "name": "pricesE8", "type": "uint256[]"}
    ], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "symbolHash", "type": "bytes32"}], "name": "getThermometer", "outputs": [
        {"internalType": "uint256", "name": "windowBlocks", "type": "uint256"},
        {"internalType": "uint256", "name": "cooldownBlocks", "type": "uint256"},
        {"internalType": "uint256", "name": "lastReportBlock", "type": "uint256"},
        {"internalType": "uint8", "name": "currentBand", "type": "uint8"},
        {"internalType": "uint256", "name": "currentVolatilityE8", "type": "uint256"},
        {"internalType": "uint256", "name": "currentPriceE8", "type": "uint256"},
        {"internalType": "bool", "name": "halted", "type": "bool"},
        {"internalType": "uint256", "name": "registeredAtBlock", "type": "uint256"},
        {"internalType": "uint256", "name": "historyLength", "type": "uint256"}
    ], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "symbolHash", "type": "bytes32"}, {"internalType": "uint256", "name": "priceE8", "type": "uint256"}], "name": "reportPrice", "outputs": [], "stateMutability": "payable", "type": "function"},
    {"inputs": [
        {"internalType": "bytes32[]", "name": "symbolHashes", "type": "bytes32[]"},
        {"internalType": "uint256[]", "name": "pricesE8", "type": "uint256[]"}
    ], "name": "batchReportPrices", "outputs": [], "stateMutability": "payable", "type": "function"},
    {"inputs": [{"internalType": "string", "name": "symbol", "type": "string"}], "name": "symbolHashFromString", "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}], "stateMutability": "pure", "type": "function"},
    {"inputs": [], "name": "getThresholds", "outputs": [
        {"internalType": "uint256", "name": "_coldBps", "type": "uint256"},
        {"internalType": "uint256", "name": "_mildBps", "type": "uint256"},
        {"internalType": "uint256", "name": "_warmBps", "type": "uint256"},
        {"internalType": "uint256", "name": "_hotBps", "type": "uint256"}
    ], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "symbolHash", "type": "bytes32"}], "name": "getCurrentBand", "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "symbolHash", "type": "bytes32"}], "name": "getCurrentPriceE8", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "symbolHash", "type": "bytes32"}], "name": "getVolatilityE8", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "symbolHash", "type": "bytes32"}, {"internalType": "uint256", "name": "offset", "type": "uint256"}, {"internalType": "uint256", "name": "limit", "type": "uint256"}], "name": "getPriceHistory", "outputs": [
        {"internalType": "uint256[]", "name": "pricesE8", "type": "uint256[]"},
        {"internalType": "uint256[]", "name": "blocks", "type": "uint256[]"}
    ], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "symbolHash", "type": "bytes32"}, {"internalType": "uint256", "name": "offset", "type": "uint256"}, {"internalType": "uint256", "name": "limit", "type": "uint256"}], "name": "getBandHistory", "outputs": [
        {"internalType": "uint8[]", "name": "bands", "type": "uint8[]"},
        {"internalType": "uint256[]", "name": "blocks", "type": "uint256[]"}
    ], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getBandStats", "outputs": [
        {"internalType": "uint256", "name": "coldCount", "type": "uint256"},
        {"internalType": "uint256", "name": "mildCount", "type": "uint256"},
        {"internalType": "uint256", "name": "warmCount", "type": "uint256"},
        {"internalType": "uint256", "name": "hotCount", "type": "uint256"},
        {"internalType": "uint256", "name": "criticalCount", "type": "uint256"}
    ], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "platformPaused", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "symbolHash", "type": "bytes32"}], "name": "isHalted", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getReportFeeWei", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getContractBalance", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint8", "name": "band", "type": "uint8"}], "name": "bandLabel", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "pure", "type": "function"},
    {"inputs": [], "name": "getHottestSymbol", "outputs": [
        {"internalType": "bytes32", "name": "symbolHash", "type": "bytes32"},
        {"internalType": "uint8", "name": "band", "type": "uint8"},
        {"internalType": "uint256", "name": "volatilityE8", "type": "uint256"}
    ], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getColdestSymbol", "outputs": [
        {"internalType": "bytes32", "name": "symbolHash", "type": "bytes32"},
        {"internalType": "uint8", "name": "band", "type": "uint8"},
        {"internalType": "uint256", "name": "volatilityE8", "type": "uint256"}
    ], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "symbolHash", "type": "bytes32"}], "name": "canReport", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getConfigSnapshot", "outputs": [
        {"internalType": "address", "name": "ownerAddr", "type": "address"},
        {"internalType": "address", "name": "treasuryAddr", "type": "address"},
        {"internalType": "address", "name": "guardianAddr", "type": "address"},
        {"internalType": "address", "name": "updaterAddr", "type": "address"},
        {"internalType": "uint256", "name": "deployBlk", "type": "uint256"},
        {"internalType": "uint256", "name": "coldBpsVal", "type": "uint256"},
        {"internalType": "uint256", "name": "mildBpsVal", "type": "uint256"},
        {"internalType": "uint256", "name": "warmBpsVal", "type": "uint256"},
        {"internalType": "uint256", "name": "hotBpsVal", "type": "uint256"},
        {"internalType": "uint256", "name": "reportFee", "type": "uint256"},
        {"internalType": "uint256", "name": "maxHistLen", "type": "uint256"},
        {"internalType": "bool", "name": "paused", "type": "bool"}
    ], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "symbolHash", "type": "bytes32"}], "name": "getSummaryForSymbol", "outputs": [
        {"internalType": "uint256", "name": "currentPriceE8", "type": "uint256"},
        {"internalType": "uint256", "name": "currentVolatilityE8", "type": "uint256"},
        {"internalType": "uint8", "name": "currentBand", "type": "uint8"},
        {"internalType": "uint256", "name": "minPriceE8", "type": "uint256"},
        {"internalType": "uint256", "name": "maxPriceE8", "type": "uint256"},
        {"internalType": "uint256", "name": "historyLength", "type": "uint256"},
        {"internalType": "bool", "name": "halted", "type": "bool"},
        {"internalType": "uint256", "name": "lastReportBlock", "type": "uint256"}
    ], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getSlotsCount", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getGlobalReportSequence", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "symbolHash", "type": "bytes32"}, {"internalType": "uint256", "name": "blockNum", "type": "uint256"}], "name": "getPriceAtBlock", "outputs": [{"internalType": "uint256", "name": "priceE8", "type": "uint256"}, {"internalType": "bool", "name": "found", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "symbolHash", "type": "bytes32"}, {"internalType": "uint256", "name": "fromBlock", "type": "uint256"}, {"internalType": "uint256", "name": "toBlock", "type": "uint256"}], "name": "getPriceChangeBps", "outputs": [{"internalType": "int256", "name": "changeBps", "type": "int256"}, {"internalType": "bool", "name": "fromFound", "type": "bool"}, {"internalType": "bool", "name": "toFound", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getGenesisHash", "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getDeployBlock", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
]

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
def config_path() -> Path:
    base = os.environ.get("KIKA_CONFIG_DIR") or os.path.expanduser("~")
    return Path(base) / CONFIG_FILENAME


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

