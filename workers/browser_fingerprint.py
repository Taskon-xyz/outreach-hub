"""
自洽的浏览器指纹体系（Browser Fingerprint Profile）

设计目标：所有指纹维度互相匹配，避免出现 UA=Mac 但语言=阿拉伯语、时区=UTC+8 但
locale=ar-SA 之类的自相矛盾配置。

当前 profile：macOS（M1）+ Chrome 136 + 简体中文 + Asia/Shanghai + Retina 1440x900。
所有维度（UA / Client Hints / 屏幕 / WebGL / Canvas / 字体 / 电池 / Cookie）皆围绕
此配置生成。

使用方式（worker 中）：
    from workers.browser_fingerprint import (
        BROWSER_ARGS, IGNORE_DEFAULT_ARGS, INIT_SCRIPT,
        CONTEXT_KWARGS, EXTRA_HTTP_HEADERS,
    )

    browser = await p.chromium.launch(
        headless=False,
        args=BROWSER_ARGS,
        ignore_default_args=IGNORE_DEFAULT_ARGS,
    )
    context = await browser.new_context(**CONTEXT_KWARGS)
    await context.add_init_script(INIT_SCRIPT)
    await context.set_extra_http_headers(EXTRA_HTTP_HEADERS)
"""
import json

# ── 1. Profile（所有指纹的事实来源） ────────────────────────────────────────
PROFILE = {
    "name": "MacBook Pro M1 / Chrome 136 / zh-CN",

    # ── 平台 & UA ───────────────────────────────────────────────────────
    "user_agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "platform": "MacIntel",
    "vendor": "Google Inc.",
    "app_version": (
        "5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),

    # ── 语言 & 时区（自洽：IP 在日本（VPN）/ 浏览器语言中文，
    #     模拟「中国人在日本上网」的真实组合 —— 时区必须和 IP 国家一致）─
    "locale": "zh-CN",
    "languages": ["zh-CN", "zh", "en-US", "en"],
    "timezone": "Asia/Tokyo",
    "accept_language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",

    # ── 屏幕 & 视口（MacBook Pro 13" Retina, 1440x900 逻辑分辨率）─────────
    "viewport_width": 1440,
    "viewport_height": 900,
    "screen_width": 1440,
    "screen_height": 900,
    "avail_width": 1440,
    "avail_height": 875,  # 减去 macOS menu bar (25px)
    "color_depth": 24,
    "pixel_depth": 24,
    "device_pixel_ratio": 2,  # Retina

    # ── Client Hints（与 UA 严格匹配 Chrome 136 / macOS）────────────────
    "ua_brands": [
        {"brand": "Chromium", "version": "136"},
        {"brand": "Google Chrome", "version": "136"},
        {"brand": "Not.A/Brand", "version": "99"},
    ],
    "ua_full_version_list": [
        {"brand": "Chromium", "version": "136.0.7103.93"},
        {"brand": "Google Chrome", "version": "136.0.7103.93"},
        {"brand": "Not.A/Brand", "version": "99.0.0.0"},
    ],
    "ua_platform": "macOS",
    "ua_platform_version": "10.15.7",
    "ua_arch": "arm",       # M1 = arm；如改 Intel 改 "x86"
    "ua_bitness": "64",
    "ua_wow64": False,
    "ua_mobile": False,
    "ua_model": "",
    "ua_full_version": "136.0.7103.93",

    # ── 硬件 ──────────────────────────────────────────────────────────
    "hardware_concurrency": 8,   # M1 Pro = 10, M1 = 8
    "device_memory": 8,
    "max_touch_points": 0,       # macOS 非触屏

    # ── WebGL（M1 / Apple Metal）─────────────────────────────────────
    "webgl_vendor": "Google Inc. (Apple)",
    "webgl_renderer": "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)",
    "webgl_unmasked_vendor": "Apple",
    "webgl_unmasked_renderer": "Apple M1",

    # ── macOS 字体（系统 + 简体中文）─────────────────────────────────
    "fonts": [
        "Andale Mono", "Arial", "Arial Black", "Arial Hebrew", "Arial Narrow",
        "Arial Rounded MT Bold", "Arial Unicode MS", "Avenir", "Avenir Next",
        "Avenir Next Condensed", "Baskerville", "Big Caslon", "Bodoni 72",
        "Bodoni 72 Oldstyle", "Bodoni 72 Smallcaps", "Bradley Hand",
        "Brush Script MT", "Chalkboard", "Chalkboard SE", "Chalkduster",
        "Charter", "Cochin", "Comic Sans MS", "Copperplate", "Courier",
        "Courier New", "Didot", "DIN Alternate", "DIN Condensed", "Futura",
        "Geneva", "Georgia", "Gill Sans", "Helvetica", "Helvetica Neue",
        "Herculanum", "Hoefler Text", "Impact", "Lucida Grande", "Luminari",
        "Marker Felt", "Menlo", "Microsoft Sans Serif", "Monaco", "Noteworthy",
        "Optima", "Palatino", "Papyrus", "Phosphate", "Rockwell",
        "Savoye LET", "SignPainter", "Skia", "Snell Roundhand", "Tahoma",
        "Times", "Times New Roman", "Trattatello", "Trebuchet MS", "Verdana",
        "Zapfino",
        # 简体中文 / CJK
        "PingFang SC", "PingFang TC", "PingFang HK", "Hiragino Sans GB",
        "Heiti SC", "Songti SC", "Songti TC", "STSong", "STHeiti", "STKaiti",
        "STFangsong", "STXihei", "Yuanti SC", "Kaiti SC",
        # 日文（macOS 自带，中文用户系统也有）
        "Hiragino Sans", "Hiragino Mincho ProN", "Hiragino Maru Gothic ProN",
        # 韩文
        "Apple SD Gothic Neo",
    ],

    # ── 电池（确定值；非充电、中等电量）─────────────────────────────────
    "battery_level": 0.87,
    "battery_charging": False,
    "battery_discharging_time": 11760,  # ≈3.27 小时

    # ── 噪声种子（用于 Canvas / Audio 指纹的确定性扰动）──────────────────
    "noise_seed": 0xC0FFEE,
}


# ── 2. Launch args（包含语言提示，影响 HTTP Accept-Language 等）────────────
BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--exclude-switches=enable-automation",
    "--disable-infobars",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=ChromeWhatsNewUI,InterestFeedContentSuggestions",
    f"--lang={PROFILE['locale']}",
    f"--accept-lang={PROFILE['accept_language']}",
    f"--window-size={PROFILE['viewport_width']},{PROFILE['viewport_height']}",
]

IGNORE_DEFAULT_ARGS = [
    "--enable-automation",
    "--enable-blink-features=IdleDetection",
]


# ── 3. Context kwargs（Playwright new_context / launch_persistent_context）─
CONTEXT_KWARGS = {
    "user_agent": PROFILE["user_agent"],
    "locale": PROFILE["locale"],
    "timezone_id": PROFILE["timezone"],
    "viewport": {
        "width": PROFILE["viewport_width"],
        "height": PROFILE["viewport_height"],
    },
    "device_scale_factor": PROFILE["device_pixel_ratio"],
    "is_mobile": False,
    "has_touch": False,
    "color_scheme": "light",
    "reduced_motion": "no-preference",
    "screen": {
        "width": PROFILE["screen_width"],
        "height": PROFILE["screen_height"],
    },
}


# ── 4. HTTP headers（Sec-CH-UA-* Client Hints）─────────────────────────────
def _brand_list(brands):
    return ", ".join(f'"{b["brand"]}";v="{b["version"]}"' for b in brands)


EXTRA_HTTP_HEADERS = {
    "Accept-Language": PROFILE["accept_language"],
    "Sec-CH-UA": _brand_list(PROFILE["ua_brands"]),
    "Sec-CH-UA-Mobile": "?1" if PROFILE["ua_mobile"] else "?0",
    "Sec-CH-UA-Platform": f'"{PROFILE["ua_platform"]}"',
    "Sec-CH-UA-Platform-Version": f'"{PROFILE["ua_platform_version"]}"',
    "Sec-CH-UA-Arch": f'"{PROFILE["ua_arch"]}"',
    "Sec-CH-UA-Bitness": f'"{PROFILE["ua_bitness"]}"',
    "Sec-CH-UA-Model": f'"{PROFILE["ua_model"]}"',
    "Sec-CH-UA-Full-Version": f'"{PROFILE["ua_full_version"]}"',
    "Sec-CH-UA-Full-Version-List": _brand_list(PROFILE["ua_full_version_list"]),
    "Sec-CH-UA-WoW64": "?0",
}


# ── 5. Init script（JS 层指纹注入；CDP & persistent context 通用）─────────
_PROFILE_JSON = json.dumps(PROFILE)

INIT_SCRIPT = (
    "(function() {"
    f"const PROFILE = {_PROFILE_JSON};"
    """
    // ─────────────────────────────────────────────────────────────
    // 工具：安全 defineProperty（容错 + 不可重定义则跳过）
    // ─────────────────────────────────────────────────────────────
    function safeDefine(obj, prop, getter) {
        try {
            Object.defineProperty(obj, prop, {
                get: getter, configurable: true, enumerable: true
            });
        } catch (e) {}
    }

    // ─────────────────────────────────────────────────────────────
    // 1. webdriver 隐藏 + iframe 内同步隐藏
    // ─────────────────────────────────────────────────────────────
    safeDefine(Navigator.prototype, 'webdriver', () => undefined);
    try { delete Navigator.prototype.__proto__.webdriver; } catch (e) {}

    try {
        const origCW = HTMLIFrameElement.prototype.__lookupGetter__('contentWindow');
        Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
            get: function () {
                const w = origCW.call(this);
                if (w && w.navigator) {
                    try { Object.defineProperty(w.navigator, 'webdriver', {get: () => undefined}); }
                    catch (e) {}
                }
                return w;
            }
        });
    } catch (e) {}

    // ─────────────────────────────────────────────────────────────
    // 2. Navigator 基础属性
    // ─────────────────────────────────────────────────────────────
    safeDefine(Navigator.prototype, 'platform',           () => PROFILE.platform);
    safeDefine(Navigator.prototype, 'vendor',             () => PROFILE.vendor);
    safeDefine(Navigator.prototype, 'appVersion',         () => PROFILE.app_version);
    safeDefine(Navigator.prototype, 'language',           () => PROFILE.languages[0]);
    safeDefine(Navigator.prototype, 'languages',          () => PROFILE.languages);
    safeDefine(Navigator.prototype, 'hardwareConcurrency',() => PROFILE.hardware_concurrency);
    safeDefine(Navigator.prototype, 'deviceMemory',       () => PROFILE.device_memory);
    safeDefine(Navigator.prototype, 'maxTouchPoints',     () => PROFILE.max_touch_points);
    safeDefine(Navigator.prototype, 'doNotTrack',         () => null);
    safeDefine(Navigator.prototype, 'cookieEnabled',      () => true);
    safeDefine(Navigator.prototype, 'onLine',             () => true);

    // ─────────────────────────────────────────────────────────────
    // 3. Client Hints (navigator.userAgentData)
    // ─────────────────────────────────────────────────────────────
    const uaData = {
        brands: PROFILE.ua_brands.map(b => ({ brand: b.brand, version: b.version })),
        mobile: PROFILE.ua_mobile,
        platform: PROFILE.ua_platform,
        getHighEntropyValues: function (hints) {
            const r = {
                brands: this.brands,
                mobile: this.mobile,
                platform: this.platform,
            };
            if (hints.includes('architecture'))     r.architecture     = PROFILE.ua_arch;
            if (hints.includes('bitness'))          r.bitness          = PROFILE.ua_bitness;
            if (hints.includes('model'))            r.model            = PROFILE.ua_model;
            if (hints.includes('platformVersion'))  r.platformVersion  = PROFILE.ua_platform_version;
            if (hints.includes('uaFullVersion'))    r.uaFullVersion    = PROFILE.ua_full_version;
            if (hints.includes('fullVersionList'))  r.fullVersionList  = PROFILE.ua_full_version_list;
            if (hints.includes('wow64'))            r.wow64            = PROFILE.ua_wow64;
            return Promise.resolve(r);
        },
        toJSON: function () {
            return { brands: this.brands, mobile: this.mobile, platform: this.platform };
        },
    };
    safeDefine(Navigator.prototype, 'userAgentData', () => uaData);

    // ─────────────────────────────────────────────────────────────
    // 4. Screen
    // ─────────────────────────────────────────────────────────────
    safeDefine(Screen.prototype, 'width',       () => PROFILE.screen_width);
    safeDefine(Screen.prototype, 'height',      () => PROFILE.screen_height);
    safeDefine(Screen.prototype, 'availWidth',  () => PROFILE.avail_width);
    safeDefine(Screen.prototype, 'availHeight', () => PROFILE.avail_height);
    safeDefine(Screen.prototype, 'colorDepth',  () => PROFILE.color_depth);
    safeDefine(Screen.prototype, 'pixelDepth',  () => PROFILE.pixel_depth);
    safeDefine(window, 'devicePixelRatio',      () => PROFILE.device_pixel_ratio);

    // ─────────────────────────────────────────────────────────────
    // 5. WebGL VENDOR / RENDERER / UNMASKED 覆盖
    // ─────────────────────────────────────────────────────────────
    function patchGetParameter(proto) {
        if (!proto) return;
        const orig = proto.getParameter;
        proto.getParameter = function (param) {
            // VENDOR=0x1F00 (7936), RENDERER=0x1F01 (7937)
            if (param === 7936) return PROFILE.webgl_vendor;
            if (param === 7937) return PROFILE.webgl_renderer;
            // UNMASKED_VENDOR_WEBGL=0x9245 (37445)
            if (param === 37445) return PROFILE.webgl_unmasked_vendor;
            // UNMASKED_RENDERER_WEBGL=0x9246 (37446)
            if (param === 37446) return PROFILE.webgl_unmasked_renderer;
            return orig.call(this, param);
        };
    }
    try { patchGetParameter(WebGLRenderingContext.prototype); } catch (e) {}
    try { if (window.WebGL2RenderingContext) patchGetParameter(WebGL2RenderingContext.prototype); } catch (e) {}

    // ─────────────────────────────────────────────────────────────
    // 6. Canvas 指纹（确定性轻噪声：seed 固定 → 同页输出稳定但与真实硬件不同）
    // ─────────────────────────────────────────────────────────────
    const NOISE_SEED = PROFILE.noise_seed;
    function mkPRNG(seed) {
        let s = seed >>> 0;
        return function () {
            s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
            return (s >>> 16) & 0xff;
        };
    }
    function addCanvasNoise(imageData) {
        const prng = mkPRNG(NOISE_SEED);
        const d = imageData.data;
        // 每 23 像素扰动一次，避免可见但破坏指纹
        for (let i = 0; i < d.length; i += 92) {
            if (d[i + 3] === 0) continue;
            d[i]     = (d[i]     ^ (prng() & 0x01)) & 0xff;
            d[i + 1] = (d[i + 1] ^ (prng() & 0x01)) & 0xff;
            d[i + 2] = (d[i + 2] ^ (prng() & 0x01)) & 0xff;
        }
    }

    try {
        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function (...args) {
            if (this.width > 0 && this.height > 0 && this.width * this.height < 4_000_000) {
                try {
                    const ctx = this.getContext('2d');
                    if (ctx) {
                        const img = ctx.getImageData(0, 0, this.width, this.height);
                        addCanvasNoise(img);
                        ctx.putImageData(img, 0, 0);
                    }
                } catch (e) {}
            }
            return origToDataURL.apply(this, args);
        };
    } catch (e) {}

    try {
        const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        CanvasRenderingContext2D.prototype.getImageData = function (...args) {
            const img = origGetImageData.apply(this, args);
            try { addCanvasNoise(img); } catch (e) {}
            return img;
        };
    } catch (e) {}

    try {
        const origToBlob = HTMLCanvasElement.prototype.toBlob;
        HTMLCanvasElement.prototype.toBlob = function (cb, ...rest) {
            if (this.width > 0 && this.height > 0 && this.width * this.height < 4_000_000) {
                try {
                    const ctx = this.getContext('2d');
                    if (ctx) {
                        const img = ctx.getImageData(0, 0, this.width, this.height);
                        addCanvasNoise(img);
                        ctx.putImageData(img, 0, 0);
                    }
                } catch (e) {}
            }
            return origToBlob.call(this, cb, ...rest);
        };
    } catch (e) {}

    // ─────────────────────────────────────────────────────────────
    // 7. 字体探测（document.fonts.check / measureText）
    // ─────────────────────────────────────────────────────────────
    const FONT_SET = new Set(PROFILE.fonts.map(f => f.toLowerCase()));
    const GENERIC_FONTS = new Set(['serif','sans-serif','monospace','cursive','fantasy','system-ui','-apple-system']);
    try {
        if (document.fonts && document.fonts.check) {
            const origCheck = document.fonts.check.bind(document.fonts);
            document.fonts.check = function (font, text) {
                const m = String(font).match(/[\\d.]+px\\s+["']?([^"',]+)["']?/);
                if (m) {
                    const fam = m[1].trim().toLowerCase();
                    if (FONT_SET.has(fam) || GENERIC_FONTS.has(fam)) return true;
                    return false;
                }
                return origCheck(font, text);
            };
        }
    } catch (e) {}

    // ─────────────────────────────────────────────────────────────
    // 8. 电池 API（稳定值；Chrome 现行版本仍在部分场景下暴露）
    // ─────────────────────────────────────────────────────────────
    const BATTERY = {
        level: PROFILE.battery_level,
        charging: PROFILE.battery_charging,
        chargingTime: PROFILE.battery_charging ? 3600 : Infinity,
        dischargingTime: PROFILE.battery_charging ? Infinity : PROFILE.battery_discharging_time,
        onchargingchange: null, onchargingtimechange: null,
        ondischargingtimechange: null, onlevelchange: null,
        addEventListener: function () {}, removeEventListener: function () {},
        dispatchEvent: function () { return true; },
    };
    try {
        if (navigator.getBattery) {
            navigator.getBattery = function () { return Promise.resolve(BATTERY); };
        } else {
            safeDefine(Navigator.prototype, 'getBattery', () => function () { return Promise.resolve(BATTERY); });
        }
    } catch (e) {}

    // ─────────────────────────────────────────────────────────────
    // 9. Plugins / MimeTypes（Chrome 默认 PDF Viewer 五件套）
    // ─────────────────────────────────────────────────────────────
    const pdfMimes = [
        { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
        { type: 'text/pdf',        suffixes: 'pdf', description: 'Portable Document Format' },
    ];
    function mkPlugin(name) {
        const p = Object.create(Plugin.prototype);
        Object.defineProperty(p, 'name',        { value: name });
        Object.defineProperty(p, 'filename',    { value: 'internal-pdf-viewer' });
        Object.defineProperty(p, 'description', { value: 'Portable Document Format' });
        Object.defineProperty(p, 'length',      { value: pdfMimes.length });
        pdfMimes.forEach((m, i) => Object.defineProperty(p, i, { value: m }));
        return p;
    }
    const pluginList = [
        mkPlugin('PDF Viewer'),
        mkPlugin('Chrome PDF Viewer'),
        mkPlugin('Chromium PDF Viewer'),
        mkPlugin('Microsoft Edge PDF Viewer'),
        mkPlugin('WebKit built-in PDF'),
    ];
    Object.setPrototypeOf(pluginList, PluginArray.prototype);
    safeDefine(Navigator.prototype, 'plugins', () => pluginList);

    // ─────────────────────────────────────────────────────────────
    // 10. window.chrome（CDP 模式下偶有缺失）
    // ─────────────────────────────────────────────────────────────
    if (!window.chrome) window.chrome = {};
    if (!window.chrome.runtime)   window.chrome.runtime   = { OnInstalledReason: {}, OnRestartRequiredReason: {}, PlatformArch: {}, PlatformNaclArch: {}, PlatformOs: {}, RequestUpdateCheckStatus: {} };
    if (!window.chrome.app)       window.chrome.app       = { InstallState: { DISABLED: 'disabled' }, RunningState: { CANNOT_RUN: 'cannot_run' }, getDetails: function () {}, getIsInstalled: function () {} };
    if (!window.chrome.csi)       window.chrome.csi       = function () { return { onloadT: Date.now(), startE: Date.now(), tran: 15 }; };
    if (!window.chrome.loadTimes) window.chrome.loadTimes = function () { return { firstPaintTime: 0, requestTime: Date.now() / 1000 }; };

    // ─────────────────────────────────────────────────────────────
    // 11. permissions.query（隐藏 CDP 暴露的不一致）
    // ─────────────────────────────────────────────────────────────
    try {
        const origQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = function (p) {
            if (p && p.name === 'notifications') {
                return Promise.resolve({ state: Notification.permission, onchange: null });
            }
            return origQuery(p);
        };
    } catch (e) {}

    // ─────────────────────────────────────────────────────────────
    // 12. Intl 时区一致性（如果 Playwright timezone_id 未生效作为兜底）
    // ─────────────────────────────────────────────────────────────
    try {
        const origResolved = Intl.DateTimeFormat.prototype.resolvedOptions;
        Intl.DateTimeFormat.prototype.resolvedOptions = function () {
            const o = origResolved.call(this);
            if (!o.timeZone || o.timeZone === 'UTC') o.timeZone = PROFILE.timezone;
            if (!o.locale)                            o.locale   = PROFILE.locale;
            return o;
        };
    } catch (e) {}

    // ─────────────────────────────────────────────────────────────
    // 13. Connection API（让 navigator.connection 与 Mac WiFi 自洽）
    // ─────────────────────────────────────────────────────────────
    try {
        const conn = {
            effectiveType: '4g', rtt: 50, downlink: 10, saveData: false, type: 'wifi',
            onchange: null, addEventListener: () => {}, removeEventListener: () => {},
        };
        safeDefine(Navigator.prototype, 'connection', () => conn);
    } catch (e) {}

    })();
    """
)
