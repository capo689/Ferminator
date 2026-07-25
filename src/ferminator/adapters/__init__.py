"""V1 ATS adapters."""

from ferminator.adapters.ashby import AshbyAdapter
from ferminator.adapters.bamboohr import BambooHRAdapter
from ferminator.adapters.greenhouse import GreenhouseAdapter
from ferminator.adapters.lever import LeverAdapter
from ferminator.adapters.smartrecruiters import SmartRecruitersAdapter
from ferminator.adapters.workable import WorkableAdapter
from ferminator.domain import ATSProvider

ADAPTERS = {
    ATSProvider.GREENHOUSE: GreenhouseAdapter,
    ATSProvider.LEVER: LeverAdapter,
    ATSProvider.ASHBY: AshbyAdapter,
    ATSProvider.SMARTRECRUITERS: SmartRecruitersAdapter,
    ATSProvider.WORKABLE: WorkableAdapter,
    ATSProvider.BAMBOOHR: BambooHRAdapter,
}

__all__ = ["ADAPTERS"]

