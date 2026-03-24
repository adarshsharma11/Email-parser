from typing import Dict, Optional
from .activity_rule_service import ActivityRuleService

class AutomationService:
    """
    Service for managing automation rules via ActivityRuleService.
    Acts as an adapter to maintain the simple key-value interface used by BookingService.
    """

    def __init__(self, activity_rule_service: ActivityRuleService):
        self.activity_rule_service = activity_rule_service

    async def is_rule_enabled(self, rule_name: str) -> bool:
        """Check if a specific rule is enabled."""
        rule = await self.activity_rule_service.get_rule_by_slug(rule_name)
        if rule:
            return rule.status if rule.status is not None else False
        return False

    async def toggle_rule(self, rule_name: str, enabled: bool) -> Dict[str, bool]:
        """Toggle a rule on or off."""
        # First find the rule
        rule = await self.activity_rule_service.get_rule_by_slug(rule_name)
        if rule:
            # Update existing rule
            await self.activity_rule_service.toggle_status(rule.id, enabled)
        
        return await self.get_all_rules()

    async def get_all_rules(self) -> Dict[str, bool]:
        """Get all rules as a simple dict."""
        rules = await self.activity_rule_service.get_rules()
        # Filter for rules that have a slug_name
        return {
            r.slug_name: (r.status if r.status is not None else False)
            for r in rules
            if r.slug_name
        }

    async def log_rule_execution(self, rule_name: str, outcome: str):
        """Log the execution of a rule."""
        await self.activity_rule_service.log_activity(rule_name, outcome)

    async def get_logs(self, page: int = 1, limit: int = 10):
        """Get execution logs."""
        return await self.activity_rule_service.get_logs(page=page, limit=limit)
