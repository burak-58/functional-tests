from __future__ import annotations

import json

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support.ui import WebDriverWait

from .config import TestConfig


class StreamAppPage:
    def __init__(self, driver: WebDriver, config: TestConfig) -> None:
        self.driver = driver
        self.config = config

    def open_play_page(self, stream_id: str, *, ll_hls: bool = False) -> None:
        page = "play.html"
        query = f"name={stream_id}&playOrder={'ll-hls' if ll_hls else 'hls'}"
        self.driver.get(f"{self.config.normalized_server_url}/{self.config.application}/{page}?{query}")

    def open_publish_page(self, stream_id: str) -> None:
        self.driver.get(f"{self.config.normalized_server_url}/{self.config.application}/index.html?id={stream_id}")

    def _switch_to_publish_frame(self) -> None:
        self.driver.switch_to.default_content()
        WebDriverWait(self.driver, 20).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "webrtc-publish-frame"))
        )

    def _publish_debug_state(self) -> str:
        script = """
            const text = (selector) => {
                const node = document.querySelector(selector);
                return node ? (node.innerText || node.textContent || "").trim() : null;
            };
            const styleShown = (selector) => {
                const node = document.querySelector(selector);
                if (!node) {
                    return null;
                }
                return window.getComputedStyle(node).display !== "none";
            };
            const adaptor = window.webRTCAdaptor || null;
            const ws = adaptor && adaptor.webSocketAdaptor ? adaptor.webSocketAdaptor : null;
            const button = document.getElementById("start_publish_button");
            const stopButton = document.getElementById("stop_publish_button");
            return {
                readyState: document.readyState,
                pageTitle: document.title,
                streamId: document.getElementById("streamId")?.value || null,
                startDisabled: button ? button.disabled : null,
                stopDisabled: stopButton ? stopButton.disabled : null,
                offlineVisible: styleShown("#offlineInfo"),
                broadcastingVisible: styleShown("#broadcastingInfo"),
                badgeText: text(".badge"),
                notifyText: text(".notifyjs-container"),
                websocketUrl: adaptor ? (adaptor.websocketURL || adaptor.websocket_url || null) : null,
                websocketConnected: ws && typeof ws.isConnected === "function" ? ws.isConnected() : null,
                websocketConnecting: ws && typeof ws.isConnecting === "function" ? ws.isConnecting() : null,
                publishStreamId: adaptor ? (adaptor.publishStreamId || null) : null,
                localVideoReadyState: document.querySelector("video")?.readyState ?? null,
                localVideoPaused: document.querySelector("video")?.paused ?? null,
            };
        """
        try:
            state = self.driver.execute_script(script)
        except WebDriverException as exc:
            return f"unable to collect publish debug state: {exc}"
        return json.dumps(state, sort_keys=True)

    def start_publishing(self) -> None:
        self._switch_to_publish_frame()
        wait = WebDriverWait(self.driver, 60)
        button = wait.until(EC.presence_of_element_located((By.ID, "start_publish_button")))
        try:
            wait.until(lambda d: button.is_enabled())
        except Exception as exc:
            raise AssertionError(
                "WebRTC publish page never enabled the Start Publishing button. "
                f"Page state: {self._publish_debug_state()}"
            ) from exc
        button.click()

    def stop_publishing(self) -> None:
        self._switch_to_publish_frame()
        wait = WebDriverWait(self.driver, 30)
        button = wait.until(EC.presence_of_element_located((By.ID, "stop_publish_button")))
        try:
            wait.until(lambda d: button.is_enabled())
        except Exception as exc:
            raise AssertionError(
                "WebRTC publish page never enabled the Stop Publishing button. "
                f"Page state: {self._publish_debug_state()}"
            ) from exc
        button.click()

    def wait_until_video_playing(self, timeout: int = 45, *, in_publish_frame: bool = False) -> None:
        if in_publish_frame:
            self._switch_to_publish_frame()
        else:
            self.driver.switch_to.default_content()
        wait = WebDriverWait(self.driver, timeout)
        wait.until(lambda d: d.execute_script("return document.querySelector('video')?.readyState || 0") >= 2)
        wait.until(lambda d: d.execute_script("return !document.querySelector('video')?.paused"))

    def capture_video_frame(self, *, in_publish_frame: bool = False) -> bytes:
        if in_publish_frame:
            self._switch_to_publish_frame()
        else:
            self.driver.switch_to.default_content()
        video = self.driver.find_element(By.CSS_SELECTOR, "video")
        return video.screenshot_as_png
