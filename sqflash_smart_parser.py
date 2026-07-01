"""
Advantech SQFlash SMART Data Parser
Based on:
  - SQFlash SMART ID Definition (SATA) v1.5.1
  - SQFlash SMART ID Definition (NVMe) v1.5
"""

import struct
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

KELVIN_OFFSET = 273.15


def kelvin_to_celsius(k: int) -> float:
    return round(k - KELVIN_OFFSET, 1)


def sectors_to_gb(sectors: int, sector_size: int = 512) -> float:
    return round(sectors * sector_size / (1024 ** 3), 2)


# ---------------------------------------------------------------------------
# SATA SMART
# ---------------------------------------------------------------------------

@dataclass
class SATASmartAttribute:
    id_hex: str
    id_dec: int
    name: str
    raw_hex: str
    parsed: dict = field(default_factory=dict)

    def _raw_bytes(self) -> bytes:
        return bytes.fromhex(self.raw_hex.zfill(12))

    def parse(self) -> dict:
        b = self._raw_bytes()
        did = self.id_dec

        if did == 1:
            self.parsed = {"uncorrectable_ecc_count": int.from_bytes(b, "big")}

        elif did == 9:
            self.parsed = {"power_on_hours": int.from_bytes(b, "big")}

        elif did == 12:
            self.parsed = {"power_cycle_count": int.from_bytes(b, "big")}

        elif did == 14:
            cap = int.from_bytes(b[3:6], "big")
            self.parsed = {
                "device_capacity_sectors": cap,
                "device_capacity_gb": sectors_to_gb(cap),
            }

        elif did == 15:
            cap = int.from_bytes(b[3:6], "big")
            self.parsed = {
                "user_capacity_sectors": cap,
                "user_capacity_gb": sectors_to_gb(cap),
            }

        elif did == 16:
            self.parsed = {"initial_spare_blocks": int.from_bytes(b[3:6], "big")}

        elif did == 17:
            self.parsed = {"remaining_spare_blocks": int.from_bytes(b[3:6], "big")}

        elif did == 100:
            self.parsed = {"total_erase_count": int.from_bytes(b[3:6], "big")}

        elif did == 168:
            self.parsed = {"sata_phy_error_count": int.from_bytes(b, "big")}

        elif did == 170:
            later = int.from_bytes(b[0:2], "big")
            early = int.from_bytes(b[4:6], "big")
            self.parsed = {"later_bad_block": later, "early_bad_block": early}

        elif did == 173:
            avg_erase = int.from_bytes(b[2:4], "big")
            max_erase = int.from_bytes(b[4:6], "big")
            self.parsed = {"avg_erase_count": avg_erase, "max_erase_count": max_erase}

        elif did in (174, 192):
            self.parsed = {"unexpected_power_loss_count": int.from_bytes(b[3:6], "big")}

        elif did == 175:
            vs_trigger       = int.from_bytes(b[0:2], "big")
            guaranteed_flush = int.from_bytes(b[2:4], "big")
            drive_status     = int.from_bytes(b[4:6], "big")
            self.parsed = {
                "voltage_stabilizer_trigger_count": vs_trigger,
                "guaranteed_flush_enabled": guaranteed_flush == 0x01,
                "drive_status_normal": drive_status == 0x00,
            }

        elif did == 194:
            max_c = int.from_bytes(b[0:2], "big")
            min_c = int.from_bytes(b[2:4], "big")
            cur_c = int.from_bytes(b[4:6], "big")
            self.parsed = {
                "current_temp_c": cur_c,
                "min_temp_c":     min_c,
                "max_temp_c":     max_c,
            }

        elif did == 202:
            self.parsed = {"ssd_life_used_pct": b[5]}

        elif did == 218:
            self.parsed = {"crc_error_count": int.from_bytes(b, "big")}

        elif did == 231:
            self.parsed = {"ssd_life_left_pct": b[5]}

        elif did == 234:
            sectors = int.from_bytes(b, "big")
            self.parsed = {
                "total_nand_read_sectors": sectors,
                "total_nand_read_gb": sectors_to_gb(sectors),
            }

        elif did == 235:
            sectors = int.from_bytes(b, "big")
            self.parsed = {
                "total_nand_written_sectors": sectors,
                "total_nand_written_gb": sectors_to_gb(sectors),
            }

        elif did == 241:
            sectors = int.from_bytes(b, "big")
            self.parsed = {
                "total_host_write_sectors": sectors,
                "total_host_write_gb": sectors_to_gb(sectors),
            }

        elif did == 242:
            sectors = int.from_bytes(b, "big")
            self.parsed = {
                "total_host_read_sectors": sectors,
                "total_host_read_gb": sectors_to_gb(sectors),
            }

        elif did == 244:
            self.parsed = {"average_erase_count_100k": int.from_bytes(b, "big")}

        elif did == 245:
            self.parsed = {"max_erase_count_100k": int.from_bytes(b, "big")}

        else:
            self.parsed = {"raw": self.raw_hex}

        return self.parsed

    def __str__(self) -> str:
        self.parse()
        return (
            f"[SATA] ID={self.id_hex}({self.id_dec:3d}) "
            f"{self.name:<42s} raw={self.raw_hex}  parsed={self.parsed}"
        )


class SATASmartParser:
    ATTR_TABLE = {
        1:   ("01h", "Raw_Read_Error_Rate"),
        9:   ("09h", "Power_On_Hours"),
        12:  ("0Ch", "Power_Cycle_Count"),
        14:  ("0Eh", "Device Capacity"),
        15:  ("0Fh", "User Capacity"),
        16:  ("10h", "Initial Spare Blocks Available"),
        17:  ("11h", "Spare Blocks Remaining"),
        100: ("64h", "Total Erase Count"),
        168: ("A8h", "SATA PHY Error Count"),
        170: ("AAh", "Bad Block Count"),
        173: ("ADh", "Erase Count"),
        174: ("AEh", "Unexpected Power Loss Count"),
        175: ("AFh", "Power Failure Protection Status"),
        192: ("C0h", "Unexpected Power Loss Count"),
        194: ("C2h", "Temperature"),
        202: ("CAh", "Percentage of Spares Remaining"),
        218: ("DAh", "CRC Error"),
        231: ("E7h", "SSD Life Remaining"),
        234: ("EAh", "Total NAND Read"),
        235: ("EBh", "Total NAND Written"),
        241: ("F1h", "Total Host Write"),
        242: ("F2h", "Total Host Read"),
        244: ("F4h", "Average Erase Count (100K PE)"),
        245: ("F5h", "Max Erase Count (100K PE)"),
    }

    def parse(self, raw_entries: list) -> list:
        result = []
        for entry in raw_entries:
            id_dec  = entry["id"]
            raw_hex = entry["raw"]
            id_hex, name = self.ATTR_TABLE.get(id_dec, (f"{id_dec:02X}h", "Unknown"))
            attr = SATASmartAttribute(id_hex, id_dec, name, raw_hex)
            attr.parse()
            result.append(attr)
        return result


# ---------------------------------------------------------------------------
# NVMe Standard SMART (Log 02h)
# ---------------------------------------------------------------------------

@dataclass
class NVMeStandardSmart:
    raw_data: bytes   # 512 bytes

    def parse(self) -> dict:
        d = self.raw_data

        def u128(o): return int.from_bytes(d[o:o+16], "little")
        def u32(o):  return int.from_bytes(d[o:o+4],  "little")
        def u16(o):  return int.from_bytes(d[o:o+2],  "little")

        composite_k = u16(1)

        result = {
            "critical_warning":                  d[0],
            "composite_temperature_K":           composite_k,
            "composite_temperature_C":           kelvin_to_celsius(composite_k),
            "available_spare_pct":               d[3],
            "available_spare_threshold_pct":     d[4],
            "percentage_used_pct":               d[5],
            "endurance_group_critical_warning":  d[6],
            "data_units_read_1k_sectors":        u128(32),
            "data_units_read_gb":                round(u128(32) * 1000 * 512 / (1024**3), 2),
            "data_units_written_1k_sectors":     u128(48),
            "data_units_written_gb":             round(u128(48) * 1000 * 512 / (1024**3), 2),
            "host_read_commands":                u128(64),
            "host_write_commands":               u128(80),
            "controller_busy_time_min":          u128(96),
            "power_cycles":                      u128(112),
            "power_on_hours":                    u128(128),
            "unsafe_shutdowns":                  u128(144),
            "media_data_integrity_errors":       u128(160),
            "num_error_log_entries":             u128(176),
            "warning_composite_temp_time_min":   u32(192),
            "critical_composite_temp_time_min":  u32(196),
        }

        sensors = {}
        for i in range(8):
            val_k = u16(200 + i * 2)
            if val_k != 0:
                sensors[i + 1] = {"K": val_k, "C": kelvin_to_celsius(val_k)}
        result["temperature_sensors"] = sensors

        cw = d[0]
        result["critical_warning_decoded"] = {
            "spare_below_threshold":       bool(cw & (1 << 0)),
            "temperature_warning":         bool(cw & (1 << 1)),
            "reliability_degraded":        bool(cw & (1 << 2)),
            "media_read_only":             bool(cw & (1 << 3)),
            "volatile_backup_failed":      bool(cw & (1 << 4)),
            "persistent_memory_readonly":  bool(cw & (1 << 5)),
        }

        return result


# ---------------------------------------------------------------------------
# NVMe Vendor SMART — 700/900 Series (Log C0h)
# ---------------------------------------------------------------------------

@dataclass
class NVMeVendor700900:
    raw_data: bytes   # 64 bytes

    def parse(self) -> dict:
        d = self.raw_data

        def u64(o): return int.from_bytes(d[o:o+8], "little")
        def u32(o): return int.from_bytes(d[o:o+4], "little")
        def u16(o): return int.from_bytes(d[o:o+2], "little")

        flash_read  = u64(0)
        flash_write = u64(8)
        cur_k  = u16(52)
        low_k  = u16(54)
        high_k = u16(56)
        ctrl_k = u16(60)

        return {
            "flash_read_sectors":        flash_read,
            "flash_read_gb":             sectors_to_gb(flash_read),
            "flash_write_sectors":       flash_write,
            "flash_write_gb":            sectors_to_gb(flash_write),
            "unc_error_count":           u64(16),
            "phy_error_count":           u32(24),
            "early_bad_block":           u32(28),
            "later_bad_block":           u32(32),
            "max_erase_count":           u32(36),
            "avg_erase_count":           u32(40),
            "current_spare_pct":         u64(44),
            "current_temp_K":            cur_k,
            "current_temp_C":            kelvin_to_celsius(cur_k),
            "lowest_temp_K":             low_k,
            "lowest_temp_C":             kelvin_to_celsius(low_k),
            "highest_temp_K":            high_k,
            "highest_temp_C":            kelvin_to_celsius(high_k),
            "controller_temp_K":         ctrl_k,
            "controller_temp_C":         kelvin_to_celsius(ctrl_k),
            "spare_blocks":              u16(62),
        }


# ---------------------------------------------------------------------------
# NVMe Vendor SMART — EU Series (Log D2h)
# ---------------------------------------------------------------------------

@dataclass
class NVMeVendorEU:
    raw_data: bytes

    def parse(self) -> dict:
        d = self.raw_data

        def u64(o): return int.from_bytes(d[o:o+8], "little")
        def u32(o): return int.from_bytes(d[o:o+4], "little")
        def u16(o): return int.from_bytes(d[o:o+2], "little")

        dev_cap  = u64(0)
        user_cap = u64(8)
        nand_r   = u64(16)
        nand_w   = u64(24)
        high_k   = u16(57)
        chip_k   = u16(167)

        return {
            "device_capacity_sectors":       dev_cap,
            "device_capacity_gb":            sectors_to_gb(dev_cap),
            "user_capacity_sectors":         user_cap,
            "user_capacity_gb":              sectors_to_gb(user_cap),
            "nand_read_sectors":             nand_r,
            "nand_read_gb":                  sectors_to_gb(nand_r),
            "nand_write_sectors":            nand_w,
            "nand_write_gb":                 sectors_to_gb(nand_w),
            "nand_erase_sector":             u64(32),
            "wear_leveling_indicator_pct":   u64(40),
            "ssd_life_used_pct":             u64(48),
            "write_protect":                 bool(d[56]),
            "highest_temp_K":                high_k,
            "highest_temp_C":                kelvin_to_celsius(high_k),
            "read_fail_count":               u32(59),
            "data_e3d_error":                u32(63),
            "phy_error_count":               u32(67),
            "total_bad_block_count":         u32(71),
            "total_early_bad_block":         u32(75),
            "total_later_bad_block":         u32(79),
            "program_fail_count":            u32(87),
            "erase_failure_count":           u32(91),
            "total_erase_count":             u64(123),
            "d2d3_max_erase_count":          u32(131),
            "d2d3_avg_erase_count":          u32(135),
            "d2d3_min_erase_count":          u32(139),
            "chip_internal_temp_K":          chip_k,
            "chip_internal_temp_C":          kelvin_to_celsius(chip_k),
            "thermal_throttling_count":      u16(169),
            "thermal_throttling_time_s":     u16(171),
        }


# ---------------------------------------------------------------------------
# NAND Endurance Reference Table
# ---------------------------------------------------------------------------

NAND_ENDURANCE = {
    "SLC":           60_000,
    "Ultra MLC":     30_000,
    "MLC":            3_000,
    "3D TLC":         3_000,
    "3D cTLC":        5_000,
    "3D sTLC BiCS3": 30_000,
    "3D sTLC BiCS4": 30_000,
    "3D sTLC BiCS5": 50_000,
    "3D sTLC 100K": 100_000,
}


# ---------------------------------------------------------------------------
# Health Assessment
# ---------------------------------------------------------------------------

def assess_sata_health(attrs: list, nand_type: str = "3D TLC") -> dict:
    endurance = NAND_ENDURANCE.get(nand_type, 3_000)
    report = {
        "nand_type":       nand_type,
        "endurance_limit": endurance,
        "warnings":        [],
    }

    by_id = {a.id_dec: a for a in attrs}

    def get(id_dec, key, default=None):
        a = by_id.get(id_dec)
        return a.parsed.get(key, default) if a else default

    life_left = get(231, "ssd_life_left_pct")
    if life_left is not None:
        report["ssd_life_left_pct"] = life_left
        if life_left < 10:
            report["warnings"].append(f"SSD life CRITICAL: only {life_left}% remaining!")
        elif life_left < 30:
            report["warnings"].append(f"SSD life LOW: {life_left}% remaining.")

    avg_erase = get(173, "avg_erase_count")
    if avg_erase is not None:
        pct = round(avg_erase / endurance * 100, 1)
        report["avg_erase_count"]      = avg_erase
        report["erase_life_used_pct"]  = pct
        if avg_erase >= endurance:
            report["warnings"].append(
                f"Avg erase ({avg_erase}) reached endurance limit ({endurance})!"
            )

    ecc = get(1, "uncorrectable_ecc_count")
    if ecc:
        report["warnings"].append(f"Uncorrectable ECC = {ecc} (should be 0).")

    crc = get(218, "crc_error_count")
    if crc:
        report["warnings"].append(f"CRC error = {crc}. Check SATA cable/connector.")

    phy = get(168, "sata_phy_error_count")
    if phy:
        report["warnings"].append(f"SATA PHY error = {phy}. Consider replacing cable.")

    cur_temp = get(194, "current_temp_c")
    if cur_temp is not None:
        report["current_temp_c"] = cur_temp
        if cur_temp > 70:
            report["warnings"].append(f"Temperature HIGH: {cur_temp}°C")

    report["status"] = (
        "HEALTHY"  if not report["warnings"] else
        "CRITICAL" if len(report["warnings"]) >= 3 else
        "WARNING"
    )
    return report


def assess_nvme_health(smart: dict, nand_type: str = "3D TLC") -> dict:
    endurance = NAND_ENDURANCE.get(nand_type, 3_000)
    report = {
        "nand_type":       nand_type,
        "endurance_limit": endurance,
        "warnings":        [],
    }

    pct_used = smart.get("percentage_used_pct", 0)
    report["percentage_used_pct"] = pct_used
    if pct_used >= 100:
        report["warnings"].append(f"NVM endurance consumed: {pct_used}%!")
    elif pct_used >= 80:
        report["warnings"].append(f"NVM endurance high: {pct_used}%.")

    spare = smart.get("available_spare_pct", 100)
    threshold = smart.get("available_spare_threshold_pct", 10)
    report["available_spare_pct"] = spare
    if spare < threshold:
        report["warnings"].append(
            f"Available spare ({spare}%) below threshold ({threshold}%)!"
        )

    media_err = smart.get("media_data_integrity_errors", 0)
    if media_err:
        report["warnings"].append(f"Media/data integrity errors: {media_err}.")

    temp_c = smart.get("composite_temperature_C", 0)
    report["composite_temperature_C"] = temp_c
    if temp_c > 70:
        report["warnings"].append(f"Temperature HIGH: {temp_c}°C")

    unsafe = smart.get("unsafe_shutdowns", 0)
    report["unsafe_shutdowns"] = unsafe

    cw = smart.get("critical_warning_decoded", {})
    if any(cw.values()):
        report["warnings"].append(f"Critical Warning bits set: {cw}")

    report["status"] = (
        "HEALTHY"  if not report["warnings"] else
        "CRITICAL" if len(report["warnings"]) >= 3 else
        "WARNING"
    )
    return report


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_sata():
    print("=" * 70)
    print("SATA SMART Demo")
    print("=" * 70)

    sample_entries = [
        {"id": 1,   "raw": "000000000000"},
        {"id": 9,   "raw": "0000000007D0"},
        {"id": 12,  "raw": "000000000064"},
        {"id": 14,  "raw": "000000F00000"},
        {"id": 15,  "raw": "000000E80000"},
        {"id": 16,  "raw": "000000000200"},
        {"id": 17,  "raw": "000000000190"},
        {"id": 100, "raw": "000000000DAC"},
        {"id": 168, "raw": "000000000000"},
        {"id": 170, "raw": "000A00000005"},
        {"id": 173, "raw": "000000640096"},
        {"id": 174, "raw": "000000000003"},
        {"id": 192, "raw": "000000000003"},
        {"id": 194, "raw": "001D0018001A"},
        {"id": 202, "raw": "000000000005"},
        {"id": 218, "raw": "000000000000"},
        {"id": 231, "raw": "00000000005F"},
        {"id": 234, "raw": "000010000000"},
        {"id": 235, "raw": "000008000000"},
        {"id": 241, "raw": "000080000000"},
        {"id": 242, "raw": "000040000000"},
    ]

    parser = SATASmartParser()
    attrs  = parser.parse(sample_entries)

    for attr in attrs:
        print(attr)

    print()
    health = assess_sata_health(attrs, nand_type="3D TLC")
    print("[SATA Health Report]")
    for k, v in health.items():
        print(f"  {k}: {v}")


def demo_nvme_standard():
    print("\n" + "=" * 70)
    print("NVMe Standard SMART Demo (Log 02h)")
    print("=" * 70)

    buf = bytearray(512)
    buf[0] = 0x00
    struct.pack_into("<H", buf, 1,   306)
    buf[3] = 80
    buf[4] = 10
    buf[5] = 5
    struct.pack_into("<Q", buf, 32,  2_000_000)
    struct.pack_into("<Q", buf, 48,  1_000_000)
    struct.pack_into("<Q", buf, 64,  5_000_000)
    struct.pack_into("<Q", buf, 80,  3_000_000)
    struct.pack_into("<Q", buf, 96,  500)
    struct.pack_into("<Q", buf, 112, 42)
    struct.pack_into("<Q", buf, 128, 8760)
    struct.pack_into("<Q", buf, 144, 2)
    struct.pack_into("<Q", buf, 160, 0)
    struct.pack_into("<Q", buf, 176, 1)
    struct.pack_into("<I", buf, 192, 0)
    struct.pack_into("<I", buf, 196, 0)
    struct.pack_into("<H", buf, 200, 309)

    smart  = NVMeStandardSmart(bytes(buf))
    result = smart.parse()

    print("[NVMe Standard SMART]")
    for k, v in result.items():
        print(f"  {k}: {v}")

    print()
    health = assess_nvme_health(result, nand_type="3D TLC")
    print("[NVMe Health Report]")
    for k, v in health.items():
        print(f"  {k}: {v}")


def demo_nvme_vendor_700_900():
    print("\n" + "=" * 70)
    print("NVMe Vendor SMART Demo — 700/900 Series (Log C0h)")
    print("=" * 70)

    buf = bytearray(64)
    struct.pack_into("<Q", buf, 0,  2_000_000)
    struct.pack_into("<Q", buf, 8,  1_000_000)
    struct.pack_into("<Q", buf, 16, 0)
    struct.pack_into("<I", buf, 24, 0)
    struct.pack_into("<I", buf, 28, 3)
    struct.pack_into("<I", buf, 32, 1)
    struct.pack_into("<I", buf, 36, 320)
    struct.pack_into("<I", buf, 40, 210)
    struct.pack_into("<Q", buf, 44, 85)
    struct.pack_into("<H", buf, 52, 306)
    struct.pack_into("<H", buf, 54, 299)
    struct.pack_into("<H", buf, 56, 327)
    struct.pack_into("<H", buf, 60, 310)
    struct.pack_into("<H", buf, 62, 120)

    vendor = NVMeVendor700900(bytes(buf))
    result = vendor.parse()

    print("[NVMe Vendor 700/900 SMART]")
    for k, v in result.items():
        print(f"  {k}: {v}")


def demo_nvme_vendor_eu():
    print("\n" + "=" * 70)
    print("NVMe Vendor SMART Demo — EU Series (Log D2h)")
    print("=" * 70)

    buf = bytearray(420)
    struct.pack_into("<Q", buf, 0,   468_750_000)
    struct.pack_into("<Q", buf, 8,   390_625_000)
    struct.pack_into("<Q", buf, 16,  100_000_000)
    struct.pack_into("<Q", buf, 24,   50_000_000)
    struct.pack_into("<Q", buf, 32,    5_000_000)
    struct.pack_into("<Q", buf, 40,            3)
    struct.pack_into("<Q", buf, 48,            3)
    buf[56] = 0
    struct.pack_into("<H", buf, 57,  328)
    struct.pack_into("<I", buf, 59,    0)
    struct.pack_into("<I", buf, 63,    0)
    struct.pack_into("<I", buf, 67,    0)
    struct.pack_into("<I", buf, 71,    5)
    struct.pack_into("<I", buf, 75,    3)
    struct.pack_into("<I", buf, 79,    2)
    struct.pack_into("<I", buf, 87,    0)
    struct.pack_into("<I", buf, 91,    0)
    struct.pack_into("<Q", buf, 123, 15_000)
    struct.pack_into("<I", buf, 131,   180)
    struct.pack_into("<I", buf, 135,   120)
    struct.pack_into("<I", buf, 139,    80)
    struct.pack_into("<H", buf, 167,  308)
    struct.pack_into("<H", buf, 169,    0)
    struct.pack_into("<H", buf, 171,    0)

    vendor = NVMeVendorEU(bytes(buf))
    result = vendor.parse()

    print("[NVMe Vendor EU Series SMART]")
    for k, v in result.items():
        print(f"  {k}: {v}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    demo_sata()
    demo_nvme_standard()
    demo_nvme_vendor_700_900()
    demo_nvme_vendor_eu()
