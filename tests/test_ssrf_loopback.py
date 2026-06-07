"""Regression tests for _is_loopback_host SSRF IPv6 bypass fix.

Covers the cases identified in the security review:
  - ::ffff:127.0.0.1  (IPv4-mapped loopback) — must be blocked (treated as loopback)
  - ::ffff:0.0.0.0    (IPv4-mapped unspecified) — not loopback, treated as remote
  - fec0::1           (site-local) — treated as remote (warning fires)
  - fe80::1           (link-local) — treated as remote (warning fires)
  - 127.0.0.1         (plain IPv4 loopback) — is loopback, no warning
  - localhost         (hostname) — is loopback, no warning
"""

from __future__ import annotations


from custom_components.culiplan.config_flow import _is_loopback_host


class TestIsLoopbackHostIPv4:
    def test_localhost_is_loopback(self) -> None:
        assert _is_loopback_host("localhost:11434") is True

    def test_127_0_0_1_is_loopback(self) -> None:
        assert _is_loopback_host("127.0.0.1:11434") is True

    def test_127_x_x_x_is_loopback(self) -> None:
        assert _is_loopback_host("127.1.2.3:11434") is True

    def test_public_ip_not_loopback(self) -> None:
        assert _is_loopback_host("8.8.8.8:11434") is False

    def test_rfc1918_not_loopback(self) -> None:
        assert _is_loopback_host("192.168.1.100:11434") is False

    def test_mdns_local_is_loopback(self) -> None:
        assert _is_loopback_host("my-server.local:11434") is True


class TestIsLoopbackHostIPv6:
    def test_ipv6_loopback_is_loopback(self) -> None:
        assert _is_loopback_host("[::1]:11434") is True

    def test_ipv4_mapped_loopback_is_loopback(self) -> None:
        """::ffff:127.0.0.1 embeds the IPv4 loopback — must be treated as loopback."""
        assert _is_loopback_host("[::ffff:127.0.0.1]:11434") is True

    def test_ipv4_mapped_loopback_hex_is_loopback(self) -> None:
        """::ffff:7f00:1 is the hex form of ::ffff:127.0.0.1."""
        assert _is_loopback_host("[::ffff:7f00:1]:11434") is True

    def test_ipv4_mapped_unspecified_not_loopback(self) -> None:
        """::ffff:0.0.0.0 maps to 0.0.0.0 which is not loopback."""
        assert _is_loopback_host("[::ffff:0.0.0.0]:11434") is False

    def test_ipv4_mapped_rfc1918_not_loopback(self) -> None:
        """::ffff:10.0.0.1 embeds RFC-1918 — not loopback, warning fires."""
        assert _is_loopback_host("[::ffff:10.0.0.1]:11434") is False

    def test_site_local_not_loopback(self) -> None:
        """fec0::/10 site-local — treat as remote so warning fires."""
        assert _is_loopback_host("[fec0::1]:11434") is False

    def test_link_local_not_loopback(self) -> None:
        """fe80::/10 link-local — treat as remote so warning fires."""
        assert _is_loopback_host("[fe80::1]:11434") is False

    def test_public_ipv6_not_loopback(self) -> None:
        assert _is_loopback_host("[2001:db8::1]:11434") is False


class TestIsLoopbackHostEdgeCases:
    def test_empty_string_not_loopback(self) -> None:
        assert _is_loopback_host("") is False

    def test_invalid_host_not_loopback(self) -> None:
        assert _is_loopback_host("not a valid endpoint!!") is False

    def test_full_url_localhost(self) -> None:
        assert _is_loopback_host("http://localhost:11434/v1") is True

    def test_full_url_public(self) -> None:
        assert _is_loopback_host("http://example.com:11434/v1") is False
