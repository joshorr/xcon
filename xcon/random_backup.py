import random
import time


class RandomBackoff:
    attempt = 0
    max_attempts: int | None = None

    _first_wait_called = False
    _already_reached_max_attempts = False

    def __init__(self, base_delay=0.35, max_delay=7, jitter_factor=0.5, *,
                 max_attempts: int | None = None):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_factor = jitter_factor
        self.max_attempts = max_attempts

    def wait(self):
        # Don't wait for the first try, that way `wait` can be called at the start of a loop
        # before anything happens.
        if not self._first_wait_called:
            self._first_wait_called = True
            return True

        max_attempts = self.max_attempts
        if max_attempts is not None and self.attempt >= max_attempts:
            if self._already_reached_max_attempts:
                raise Exception(f'Called wait twice in a row while at max attempts.')
            self._already_reached_max_attempts = True
            return False

        wait_time = self.calculate_random_backoff()
        time.sleep(wait_time)
        self.attempt += 1
        return True

    def reset(self):
        """ Reset attempt/try, including how by default we will not wait for first `wait()`
        call if it was
            originally configured that way (it's on by default).
        """
        self._first_wait_called = False
        self.attempt = 0

    @property
    def on_try(self) -> int:
        return self.attempt + 1

    def calculate_random_backoff(self):
        """
        Calculates a random backoff delay with exponential growth and jitter.

        Args:
            retries (int): The current number of retry attempts.
            base_delay (int): The initial delay in seconds.
            max_delay (int): The maximum allowed delay in seconds.
            jitter_factor (float): A factor to introduce randomness (0.0 to 1.0).

        Returns:
            float: The calculated delay in seconds.
        """
        # Exponential backoff calculation
        delay = self.base_delay * (2 ** self.attempt)

        # Introduce jitter
        jitter_range = delay * self.jitter_factor
        delay += random.uniform(-jitter_range, jitter_range)

        # Cap the delay at the maximum allowed
        return min(delay, self.max_delay)


