"""Object catalog statuses beyond the active runtime template library."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .object_model import ObjectFamily, SystemDependency


@dataclass(frozen=True)
class DeferredObjectSpec:
    semantic_type: str
    family: ObjectFamily
    required_systems: tuple[SystemDependency, ...]
    reason: str


DEFERRED_OBJECTS: dict[str, DeferredObjectSpec] = {
    "window": DeferredObjectSpec("window", ObjectFamily.ENVIRONMENT_CONTROL, (SystemDependency.ENVIRONMENT, SystemDependency.WEATHER), "开窗需要温度、湿度、天气和通风转移"),
    "blinds": DeferredObjectSpec("blinds", ObjectFamily.ENVIRONMENT_CONTROL, (SystemDependency.ENVIRONMENT,), "百叶窗需要透光/遮挡或环境交换语义"),
    "stoveburner": DeferredObjectSpec("stoveburner", ObjectFamily.APPLIANCE, (SystemDependency.COOKING,), "炉灶组件需要 heat source 和烹饪闭环"),
    "pan": DeferredObjectSpec("pan", ObjectFamily.COOKWARE, (SystemDependency.COOKING,), "锅具需要加热、容量和烹饪状态"),
    "pot": DeferredObjectSpec("pot", ObjectFamily.COOKWARE, (SystemDependency.COOKING,), "锅具需要加热、容量和烹饪状态"),
    "knife": DeferredObjectSpec("knife", ObjectFamily.UTENSIL, (SystemDependency.TOOL_USE,), "刀具需要切割工具使用规则"),
    "butterknife": DeferredObjectSpec("butterknife", ObjectFamily.UTENSIL, (SystemDependency.TOOL_USE,), "黄油刀需要切割效果"),
    "candle": DeferredObjectSpec("candle", ObjectFamily.LIGHTING, (SystemDependency.LIGHTING, SystemDependency.ALARM), "蜡烛需要点火、燃烧计时和光照效果"),
    "desklamp": DeferredObjectSpec("desklamp", ObjectFamily.LIGHTING, (SystemDependency.LIGHTING,), "台灯需要光照传播或可见性效果"),
    "floorlamp": DeferredObjectSpec("floorlamp", ObjectFamily.LIGHTING, (SystemDependency.LIGHTING,), "落地灯需要光照传播或可见性效果"),
    "alarmclock": DeferredObjectSpec("alarmclock", ObjectFamily.ALARM_DEVICE, (SystemDependency.ALARM,), "闹钟需要周期计时和 NPC 联动"),
    "spraybottle": DeferredObjectSpec("spraybottle", ObjectFamily.CLEANING_TOOL, (SystemDependency.TOOL_USE,), "喷雾需要液体、按压和目标状态效果"),
    "dishsponge": DeferredObjectSpec("dishsponge", ObjectFamily.CLEANING_TOOL, (SystemDependency.TOOL_USE,), "海绵需要湿度和工具化清洁效果"),
    "soapbottle": DeferredObjectSpec("soapbottle", ObjectFamily.CLEANING_TOOL, (SystemDependency.CONSUMPTION,), "肥皂瓶需要分配和消耗语义"),
    "toiletpaper": DeferredObjectSpec("toiletpaper", ObjectFamily.CLEANING_TOOL, (SystemDependency.CONSUMPTION,), "卫生纸需要使用和消耗语义"),
    "coffeemachine": DeferredObjectSpec("coffeemachine", ObjectFamily.APPLIANCE, (SystemDependency.COOKING, SystemDependency.CONSUMPTION), "咖啡机需要制作饮品和资源消耗"),
    "cd": DeferredObjectSpec("cd", ObjectFamily.MEDIA_DEVICE, (SystemDependency.MEDIA,), "CD 需要播放器和播放状态"),
    "creditcard": DeferredObjectSpec("creditcard", ObjectFamily.PERSONAL_ITEM, (SystemDependency.PAYMENT,), "信用卡需要刷卡机和支付系统"),
}


def deferred_systems() -> set[str]:
    return {system.value for item in DEFERRED_OBJECTS.values() for system in item.required_systems}


__all__ = ["DEFERRED_OBJECTS", "DeferredObjectSpec", "deferred_systems"]
