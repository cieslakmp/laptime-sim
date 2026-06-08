"""Abstract vehicle model interface."""

from abc import ABC, abstractmethod


class VehicleModel(ABC):
    """Base class for all vehicle models.

    Any concrete vehicle model must answer two questions at each QSS station:
      1. What is the maximum lateral acceleration available?
      2. Given the current lateral load, what are the longitudinal accel limits?
    """

    @abstractmethod
    def longitudinal_limits(
        self,
        v: float,
        ay: float,
        kappa: float,
        banking: float = 0.0,
    ) -> tuple[float, float]:
        """Return (a_min, a_max) [m/s²] for given state.

        a_min is negative (deceleration), a_max is positive (acceleration).
        """
        ...

    @abstractmethod
    def lateral_limit(
        self,
        v: float,
        kappa: float = 0.0,
        banking: float = 0.0,
    ) -> float:
        """Return maximum |ay| [m/s²] at the given speed."""
        ...

    @property
    @abstractmethod
    def mass(self) -> float:
        """Vehicle mass [kg]."""
        ...
