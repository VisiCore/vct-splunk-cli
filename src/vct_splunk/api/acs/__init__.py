"""Splunk Cloud ACS (adminconfig/v2) client and operations.

Reads are unrestricted; writes exist for index/role/hec-token create, update,
and delete but are opt-in and gated -- see
:func:`vct_splunk.commands.write.refuse_cloud_write`.
"""
