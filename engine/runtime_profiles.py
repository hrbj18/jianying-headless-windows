"""Reviewed application identities; never infer compatibility from a version prefix."""
PRIMARY_VERSION = '11.5.0'
PROFILE_PREFIX = 'jy14-headless-macos-'
WINDOWS_PROFILE = 'jy14-headless-windows-11.5.0.14471'
WINDOWS_1147_PROFILE = 'jy14-headless-windows-11.4.7.14462'
PROFILES = {
    '11.5.0': '2041482a1aaeffa4d8bd69b836f8cf38807aaad8021bca410d567c59af3bccfa',
    '11.4.2': '632c8ddd09ff4a54f876cd8142eb505055ee26d944199506b230949b7e106bd1',
    '11.4.0': 'a1693070036a6678bb5db35f71d2105812ad24a2370e7e91c78712cc0d6455f3',
}
MACOS_EXPORT_PROFILES = frozenset(PROFILE_PREFIX + v for v in ('11.5.0', '11.4.2'))
WINDOWS_EXPORT_PROFILES = frozenset((WINDOWS_PROFILE, WINDOWS_1147_PROFILE))
EXPORT_PROFILES = MACOS_EXPORT_PROFILES | WINDOWS_EXPORT_PROFILES
RESOURCE_CAPTURE_PROFILE = PROFILE_PREFIX + '11.4.2'
TIMELINE_SCHEMAS = frozenset((('185.0.0', 360000), ('187.0.0', 360000)))


def validate_timeline_schema(timeline, runtime_profile=None):
    schema = (timeline.get('new_version'), timeline.get('version'))
    if type(schema[1]) is not int or schema not in TIMELINE_SCHEMAS:
        raise ValueError('Unexpected native timeline version')
    if runtime_profile is not None:
        known = {PROFILE_PREFIX + version for version in PROFILES} | WINDOWS_EXPORT_PROFILES
        # Both schemas were read back and rendered on the exact Windows 11.4.7 build.
        reviewed_187 = {PROFILE_PREFIX + '11.5.0'} | WINDOWS_EXPORT_PROFILES
        if runtime_profile not in known or (schema[0] == '187.0.0' and
                                           runtime_profile not in reviewed_187):
            raise ValueError('Native timeline schema is incompatible with this runtime profile')
    return schema


def saved_schema_upgrade(expected, actual, runtime_profile):
    """Recognize only the exact observed UI upgrade; never normalize other fields."""
    before = validate_timeline_schema(expected, runtime_profile)
    after = validate_timeline_schema(actual, runtime_profile)
    if before == after:
        return None
    if (runtime_profile == PROFILE_PREFIX + '11.5.0' and before == ('185.0.0', 360000)
            and after == ('187.0.0', 360000)
            and actual.get('last_modified_platform', {}).get('app_version') == '11.5.0'):
        return {'timeline_id': actual['id'], 'before': before[0], 'after': after[0]}
    raise ValueError('Unreviewed native schema migration')


def validate_identity(info, fingerprint):
    version = info.get('CFBundleShortVersionString')
    if (version not in PROFILES or info.get('CFBundleVersion') != version
            or info.get('CFBundleIdentifier') != 'com.lemon.lvpro'):
        raise ValueError('Unsupported Jianying version/build/identity; stop native writes')
    if fingerprint != PROFILES[version]:
        raise ValueError('Editor library differs from its exact headless runtime profile; version='
                         + version + '; actual=' + str(fingerprint) + '; expected=' + PROFILES[version]
                         + '. Collect a redacted report with python3 tools/runtime_report.py. '
                         'This build needs review; do not replace the expected hash.')
    return version


def validate_export_profiles(build_profile, runtime_profile):
    if build_profile not in EXPORT_PROFILES or runtime_profile not in EXPORT_PROFILES:
        raise ValueError('No reviewed native export ABI for this build/runtime profile')
    if build_profile != runtime_profile:
        raise ValueError('Build runtime differs from the installed editor; rebuild or edit a copy on the current runtime')


def validate_resource_profile(runtime_profile, capture_profile):
    if capture_profile != RESOURCE_CAPTURE_PROFILE or runtime_profile not in MACOS_EXPORT_PROFILES:
        raise ValueError('Native resources need a reviewed runtime profile/capture pairing')
