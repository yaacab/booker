"""Fail-closed stubs for Yandex ID / VK ID until owner registers apps."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["auth-oauth"])


@router.get("/auth/yandex/start")
def yandex_start():
    raise HTTPException(
        503,
        "Яндекс ID не настроен: нет client_id/secret и Redirect URI от владельца",
    )


@router.get("/auth/yandex/callback")
def yandex_callback():
    raise HTTPException(503, "Яндекс ID callback выключен до настройки провайдера")


@router.get("/auth/vk/start")
def vk_start():
    raise HTTPException(
        503,
        "VK ID не настроен: нет client_id/secret и Redirect URI от владельца",
    )


@router.get("/auth/vk/callback")
def vk_callback():
    raise HTTPException(503, "VK ID callback выключен до настройки провайдера")
