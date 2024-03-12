# -*- coding: utf-8 -*-
import gazu
import pyblish.api
import re


class IntegrateKitsuNote(pyblish.api.ContextPlugin):
    """Integrate Kitsu Note"""

    order = pyblish.api.IntegratorOrder
    label = "Kitsu Note and Status"
    families = ["render", "image", "online", "plate", "kitsu", "review"]

    # status settings
    set_status_note = False
    note_status_shortname = "wfa"
    status_change_conditions = {
        "status_conditions": [],
        "family_requirements": [],
    }

    # comment settings
    custom_comment_template = {
        "enabled": False,
        "comment_template": "{comment}",
    }

    _processed_tasks = []

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

    def get_settings_from_context(self, context):
        """Get settings from context if they're different.

        As we sometimes have wrong loaded settings in this integrator,
        but have the good ones loaded in the context, it's better to use them.
        """
        kitsu_note = (
            context.data["project_settings"]
            .get("kitsu", {})
            .get("publish", {})
            .get(self.__class__.__name__, {})
        )

        settings_from_context = {}
        if kitsu_note.get("set_status_note") != self.set_status_note:
            self.set_status_note = kitsu_note["set_status_note"]
            settings_from_context["set_status_note"] = self.set_status_note

        if (
            kitsu_note.get("note_status_shortname")
            != self.note_status_shortname
        ):
            self.note_status_shortname = kitsu_note["note_status_shortname"]
            settings_from_context["note_status_shortname"] = (
                self.note_status_shortname
            )

        if (
            kitsu_note.get("status_change_conditions")
            != self.status_change_conditions
        ):
            self.status_change_conditions = kitsu_note[
                "status_change_conditions"
            ]
            settings_from_context["status_change_conditions"] = (
                self.status_change_conditions
            )

        if settings_from_context:
            self.log.info(
                "Following settings were loaded from context as they were "
                "different from loaded project settings."
            )
            for setting_name, setting_value in settings_from_context.items():
                self.log.info(f"- {setting_name}: {setting_value}")

    def skip_instance(self, context, instance, kitsu_task: dict) -> bool:
        """Define if the instance needs to be skipped or not.

        Returns:
            bool: True if the instance needs to be skipped. Else False.
        """
        # Check already existing comment
        if context.data.get("kitsu_comment"):
            self.log.info(
                "Kitsu comment already set, "
                "skipping comment creation for instance..."
            )
            return True

        # Check kitsu task
        if not kitsu_task:
            self.log.warning("No kitsu task.")
            return True
        elif kitsu_task in self._processed_tasks:
            self.log.info(
                "Kitsu task already processed, "
                "skipping comment creation for instance..."
            )
            return True

        # Check family and families
        families = set(
            [instance.data["family"]] + instance.data.get("families", [])
        )
        if (getattr(self, "family", None) and self.family not in families) or (
            getattr(self, "families", [])
            and not any(f in families for f in self.families)
        ):
            self.log.info(
                "Instance family or families doesn't match integrator, "
                "skipping comment creation for instance..."
            )
            return True
        return False

    def process(self, context):
        # Force Kitsu note settings as they're sometimes
        # not loaded correctly when using rez
        self.get_settings_from_context(context)

        for instance in context:
            kitsu_task = instance.data.get("kitsu_task")
            if self.skip_instance(context, instance, kitsu_task):
                continue

            # Get note status, by default uses the task status for the note
            # if it is not specified in the configuration
            shortname = kitsu_task["task_status"]["short_name"].upper()
            note_status = kitsu_task["task_status_id"]

            # Check if any status condition is not met
            allow_status_change = True
            for status_cond in self.status_change_conditions[
                "status_conditions"
            ]:
                condition = status_cond["condition"] == "equal"
                match = status_cond["short_name"].upper() == shortname
                if match and not condition or condition and not match:
                    allow_status_change = False
                    break

            if allow_status_change:
                # Get families
                families = {
                    instance.data.get("family")
                    for instance in context
                    if instance.data.get("publish")
                }

                # Check if any family requirement is met
                for family_requirement in self.status_change_conditions[
                    "family_requirements"
                ]:
                    condition = family_requirement["condition"] == "equal"

                    for family in families:
                        match = family_requirement["family"].lower() == family
                        if match and not condition or condition and not match:
                            allow_status_change = False
                            break

                    if allow_status_change:
                        break

            # Set note status
            if self.set_status_note and allow_status_change:
                kitsu_status = gazu.task.get_task_status_by_short_name(
                    self.note_status_shortname
                )
                if kitsu_status:
                    note_status = kitsu_status
                    self.log.info("Note Kitsu status: {}".format(note_status))
                else:
                    self.log.info(
                        f"Cannot find {self.note_status_shortname} status. "
                        f"The status will not be changed!"
                    )
            else:
                self.log.info(
                    "Don't update status note. "
                    f"{self.set_status_note = }, {allow_status_change = }"
                )

            # Get comment text body
            publish_comment = instance.data.get("comment")
            if self.custom_comment_template["enabled"]:
                publish_comment = self.format_publish_comment(instance)

            if not publish_comment:
                self.log.info("Comment is not set.")
            else:
                self.log.debug("Comment is `{}`".format(publish_comment))

            # Add comment to kitsu task
            self.log.debug(
                "Add new note in tasks id {}".format(kitsu_task["id"])
            )
            kitsu_comment = gazu.task.add_comment(
                kitsu_task, note_status, comment=publish_comment
            )

            context.data["kitsu_comment"] = kitsu_comment
            self._processed_tasks.append(kitsu_task)
