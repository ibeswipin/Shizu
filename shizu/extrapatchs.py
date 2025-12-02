# Shizu Copyright (C) 2023-2024  AmoreForever

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import logging
from .utils import (
    answer,
    get_args,
    get_args_raw,
    get_args_html,
)

logging = logging.getLogger(__name__)


class MessageMagic:
    def __init__(self, message, app) -> None:
        self.message = message
        self.app = app

        self._init_msg()

    def _init_msg(self):
        """
        Initializes the `message` object with various methods and attributes.

        Parameters:
            None

        Returns:
            None

        Raises:
            Exception: If there is an error initializing the `MessageMagic` module.

        Side Effects:
            Sets the `answer` attribute of the `message` object.
            Sets the `get_args` attribute of the `message` object.
            Sets the `get_args_raw` attribute of the `message` object.
            Sets the `get_args_html` attribute of the `message` object.
            Logs a success message if initialization is successful.
            Logs an error message if there is an error initializing `MessageMagic`.
        """
        try:
            self.message.answer = answer
            self.message.app = self.app
            self.message.client = self.app
            self.message.get_args = get_args
            self.message.get_args_raw = get_args_raw
            self.message.get_args_html = get_args_html
            self.message.inline = self.app._inline

        except Exception as e:
            logging.error(f"Error initializing MessageMagic: {str(e)}")
