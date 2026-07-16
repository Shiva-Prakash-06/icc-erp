# V1 Archive and Deletion Record

Archive date: 2026-07-16  
Source folder: `/Users/Shiva_1/Desktop/ICC ERP/icc-platform`  
Decision: the local source folder may be deleted after the checks below; the archive artifacts must be retained.

## Immutable archive evidence

- Branch: `archive/v1-final`
- Commit: `2abda51b9fcf8db4b803d814da5d5d1185b03769`
- Bundle: `/Users/Shiva_1/Desktop/ICC ERP/archive/icc-platform-v1-final.bundle`
- SHA-256 file: `/Users/Shiva_1/Desktop/ICC ERP/archive/icc-platform-v1-final.bundle.sha256`
- Bundle SHA-256: `fea75a7b655bdf26b281aba384edae2fad368351de8e319cf5036ce5c875d736`

`git bundle verify` confirmed that the bundle contains the complete repository history. A clean clone restored from the bundle passed `git fsck`, resolved to the archived commit, and contained the expected database, project workflow, and PWA files.

## Capability preservation gates

| Gate | Result |
|---|---|
| Complete current v1 state committed | Passed |
| Bundle and checksum stored outside v1 folder | Passed |
| Capability inventory recorded in the authoritative PRD | Passed |
| Project components carried forward | Passed |
| Scoped permission concepts carried forward | Passed |
| Public feedback carried forward | Passed |
| PWA readiness carried forward with safer caching boundaries | Passed |
| Magazine, journey timeline, and engagement score recorded as deferred | Passed |
| Archive restoration tested | Passed |

## Restore procedure

```bash
git clone "/Users/Shiva_1/Desktop/ICC ERP/archive/icc-platform-v1-final.bundle" restored-icc-platform-v1
cd restored-icc-platform-v1
git switch archive/v1-final
git fsck --full
```

Verify the bundle checksum before restoration:

```bash
cd "/Users/Shiva_1/Desktop/ICC ERP/archive"
shasum -a 256 -c icc-platform-v1-final.bundle.sha256
```

Deleting the local v1 folder does not authorize deleting the bundle, checksum, archive branch from any remote, or the capability inventory in the PRD.
