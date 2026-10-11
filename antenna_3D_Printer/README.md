# 3-Antenna WiFi Fixture

이 설계는 Intel WiFi Link 5300 3x3 MIMO 카드와 DANT-02SPR-BX 안테나 3개를 TX/RX에서 같은 위치로 고정하기 위한 3D 프린터용 지그입니다.

## 기본 치수

- 안테나 수: 3개
- 안테나 중심 간격: `62.5 mm`
- SMA 고정판 높이: `160 mm`
- 박스 폭: `169 mm`
- 박스 깊이: `60 mm`
- 안테나 몸통 가이드: `8.8 mm` 슬롯
- SMA 관통 구멍: `6.8 mm`

## 출력 파일

OpenSCAD에서 [antenna_mount.scad](antenna_mount.scad)를 열고 `part` 값을 바꿔 STL을 각각 내보냅니다.

```scad
part = "body";
```

```scad
part = "guide_lock";
```

TX용으로 `body` 1개와 `guide_lock` 1개, RX용으로 같은 세트를 한 번 더 출력합니다.

## 조립

1. SMA female bulkhead pigtail 3개를 상단 구멍에 끼우고 너트로 고정합니다.
2. 1.13 coax 케이블은 내부 zip-tie anchor에 케이블타이로 묶습니다.
3. DANT-02SPR-BX 안테나 3개를 SMA에 체결하고 수직으로 세웁니다.
4. 안테나 몸통을 상단 U 슬롯에 넣습니다.
5. `guide_lock`을 M3 나사 2개로 고정해 안테나가 슬롯 밖으로 빠지지 않게 합니다.

## 필요한 부품

- SMA female bulkhead to U.FL/IPEX 1.13 coax pigtail 3개
- DANT-02SPR-BX 안테나 3개
- M3 나사 2개, 권장 길이 `12~16 mm`
- 작은 케이블타이 3개
- 베이스 고정용 M4 나사 4개 또는 양면테이프/클램프

## 조정할 변수

- 실제 SMA 나사부가 빡빡하면 `sma_hole_d`를 `7.0`으로 키웁니다.
- 안테나 몸통이 빡빡하면 `guide_clearance`를 `1.0~1.2`로 키웁니다.
- 더 높은 지그가 필요하면 `body_height`를 키웁니다.
- 실험 조건상 다른 간격을 쓰려면 `antenna_spacing`만 바꿉니다. TX/RX는 반드시 같은 값으로 출력해야 합니다.

## 주의

25 cm pigtail은 `160 mm` 높이 지그에서 여유가 많지 않을 수 있습니다. PC 카드 위치에서 박스까지 옆 거리까지 생기면 케이블 장력이 커질 수 있으니, 가능하면 `30~50 cm` pigtail을 쓰는 편이 안전합니다.
