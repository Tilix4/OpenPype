# -*- coding: utf-8 -*-
import gazu
import pyblish.api
import re

from openpype.modules.kitsu.plugins.publish import integrate_kitsu_review


class IntegrateKitsuComment(pyblish.api.InstancePlugin):
    """Integrate Kitsu Comment"""

    order = integrate_kitsu_review.IntegrateKitsuReview.order
    label = "Kitsu Comment"
    families = integrate_kitsu_review.IntegrateKitsuReview.families

    # comment settings
    custom_comment_template = {
        "enabled": False,
        "comment_template": "{comment}",
    }

    def format_publish_comment(self, instance):
        """Format the instance's publish comment.

        Formats `instance.data` against the custom template.
        """

        def replace_missing_key(match):
            """If key is not found in kwargs, set None instead"""
            key = match.group(1)
            if key not in instance.data:
                self.log.warning(
                    "Key '{}' was not found in instance.data "
                    "and will be rendered as an empty string "
                    "in the comment".format(key)
                )
                return ""
            else:
                return str(instance.data[key])

        template = self.custom_comment_template["comment_template"]
        pattern = r"\{([^}]*)\}"
        return re.sub(pattern, replace_missing_key, template)

    def process(self, instance):
        # Check instance has comment
        if not (kitsu_comment := instance.data.get("kitsu_comment")):
            self.log.info(
                "No Kitsu comment found, skipping comment update for "
                f"instance {instance.data['family']}"
            )

        # Get comment text body
        instance_comment = instance.data.get("comment", "")
        if self.custom_comment_template["enabled"]:
            instance_comment = self.format_publish_comment(instance)

        if not instance_comment:
            self.log.info("Comment is not set.")
        else:
            self.log.debug(f"Comment is `{instance_comment}`")

        # Check if comment must be updated
        if kitsu_comment["text"] != instance_comment:
            self.log.info(
                "Kitsu comment is different from the one in the instance, "
                "updating comment..."
            )

            kitsu_comment["text"] = instance_comment

        # Check if comment status must be updated
        note_status_shortname = instance.data.get("note_status_shortname")
        if (
            note_status_shortname
            and note_status_shortname
            != kitsu_comment["task_status"]["short_name"]
        ):
            self.log.info(
                "Kitsu comment status is different from the one in the "
                "instance, updating comment status..."
            )
            if kitsu_status := gazu.task.get_task_status_by_short_name(
                note_status_shortname
            ):
                kitsu_comment["task_status_id"] = kitsu_status["id"]
                self.log.info(f"Note Kitsu status: {kitsu_status}")
            else:
                self.log.info(
                    f"Cannot find {note_status_shortname} status. "
                    f"The status will not be changed!"
                )

        # Update comment in kitsu task
        gazu.task.update_comment(kitsu_comment)
