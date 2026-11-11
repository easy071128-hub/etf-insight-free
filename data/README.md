# ETF 기본 목록 내장 스냅샷

이 폴더는 **저작권과 공개 재배포 조건이 검토된** KRX ETF 전종목 기본정보의 검증된 스냅샷을 배포할 때 사용합니다.

필요한 두 파일은 `etf_catalog.csv`, `etf_catalog_meta.json`입니다. 현재는 원본 파일이 저장소에 없어 **기본 데이터가 아직 미탑재** 상태이며, 사이트는 기존처럼 이용자의 파일 업로드를 지원합니다.

기존 KRX의 **ETF → 전종목 기본정보** 파일을 확보한 경우 개인 연구용 변환 명령:

```bash
python scripts/build_etf_catalog.py data_0259_20261111.xlsx --observed-on 2026-11-11
```

기본 결과는 `private_data/`에 저장되며 **공개 GitHub에 올리면 안 됩니다.** 17개 원본 컬럼과 자료 수, SHA256, 다운로드일 기록이 보존됩니다.

KRX 홈페이지 이용약관 제12조는 사전 허락 없는 정보 배포를 제한합니다. **실제 서면 재배포 허락을 확보한 이후에만** 다음과 같이 승인 스냅샷을 만들 수 있습니다.

```bash
python scripts/build_etf_catalog.py data_0259_20261111.xlsx --observed-on 2026-11-11 --output-dir data --authorize-publication --permission-reference "실제 허가문서/계약번호"
```

승인된 자료가 GitHub `data/`에 반영되면 방문자 모두에게 검색용 ETF 목록이 자동 제공됩니다. 허가 문서가 없다면 승인 플래그를 사용하지 마세요.

- ETF 기본정보와 **실제 ETF 편입종목/NAV 편입비중은 다릅니다.**
- 시장이 변하면 새로운 KRX 원본으로 갱신해야 합니다.
- KRX 원본의 법적 사용 조건은 코드가 자동으로 승인해 주지 않습니다.
- 공개 기본정보를 세션에 복사하므로 방문자별 업로드 자료는 혼합하지 않습니다.
