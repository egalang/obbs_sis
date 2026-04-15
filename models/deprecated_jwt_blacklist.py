from odoo import models, fields


class JWTTokenBlacklist(models.Model):
    _name = "sis.jwt.blacklist"
    _description = "JWT Token Blacklist"

    jti = fields.Char(string="Token ID", required=True, index=True)
    user_id = fields.Many2one("res.users", string="User", required=True)
    blacklisted_on = fields.Datetime(
        string="Blacklisted On", default=fields.Datetime.now
    )
