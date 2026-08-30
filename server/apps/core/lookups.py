from django.db.models import CharField, Field, TextField
from django.db.models.lookups import PatternLookup


class ILike(PatternLookup):
    """PostgreSQL-native, case-insensitive LIKE (ILIKE) lookup."""

    lookup_name = "ilike"
    param_pattern = "%%%s%%"
    prepare_rhs = False

    def process_lhs(self, compiler, connection, lhs=None):
        sql, params = super().process_lhs(compiler, connection, lhs)
        # ILIKE requires text operands, so cast non-character fields.
        if not isinstance(self.lhs.output_field, (CharField, TextField)):
            return f"{sql}::text", list(params)
        return sql, params

    def get_rhs_op(self, connection, rhs):
        return f"ILIKE {rhs}"


Field.register_lookup(ILike)
