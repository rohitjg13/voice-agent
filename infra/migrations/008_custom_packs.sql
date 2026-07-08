-- 008: custom per-org industry packs.
-- NULL org_id = global built-in packs (seeded from YAML).
-- Non-NULL org_id = org-scoped custom packs.

ALTER TABLE pack_templates ADD COLUMN org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;
CREATE INDEX pack_templates_org_idx ON pack_templates (org_id);
