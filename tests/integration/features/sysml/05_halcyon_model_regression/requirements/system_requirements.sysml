package 'Halcyon dPCR-24 system requirements' {
    doc /*
     * System requirements of the dPCR-24 analyser. Each requirement is
     * derived from a stakeholder requirement. Measured attributes are
     * filled by simulation or by model checks in the verification package.
     */

    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;
    private import 'Halcyon dPCR-24 stakeholder requirements'::**;

    package 'Throughput' {
        doc /*
         * Samples per shift and equipment load.
         */

        requirement <'SYS-THR-001'> 'Shift throughput' {
            doc /*
             * The instrument shall complete at least 96 samples in an
             * 8-hour shift at nominal load.
             */
            attribute requiredSamplesPerShift : Real = 96;
            attribute measuredSamplesPerShift : Real;
            require constraint {
                measuredSamplesPerShift >= requiredSamplesPerShift
            }
        }

        requirement <'SYS-UTL-001'> 'Imager utilisation' {
            doc /*
             * The instrument shall keep the mean utilisation of the
             * fluorescence imagers at or below 85% at nominal load.
             */
            attribute requiredImagerUtilisation : Real = 0.85;
            attribute measuredImagerUtilisation : Real;
            require constraint {
                measuredImagerUtilisation <= requiredImagerUtilisation
            }
        }

        dependency from 'SYS-THR-001' to 'STK-THR-001';
        dependency from 'SYS-UTL-001' to 'STK-THR-001';
    }

    package 'Turnaround' {
        doc /*
         * Time from loading to reported result.
         */

        requirement <'SYS-TAT-001'> 'Time to first result' {
            doc /*
             * The instrument shall report the first result of a batch
             * within 90 minutes of batch loading.
             */
            attribute requiredTimeToFirstResult : DurationValue = 90 [min];
            attribute measuredTimeToFirstResult : DurationValue;
            require constraint {
                measuredTimeToFirstResult <= requiredTimeToFirstResult
            }
        }

        requirement <'SYS-TAT-002'> 'Mean turnaround' {
            doc /*
             * The instrument shall keep the mean turnaround at or below
             * 2.5 hours at nominal load.
             */
            attribute requiredMeanTurnaround : DurationValue = 2.5 [h];
            attribute measuredMeanTurnaround : DurationValue;
            require constraint {
                measuredMeanTurnaround <= requiredMeanTurnaround
            }
        }

        requirement <'SYS-TAT-003'> 'STAT turnaround' {
            doc /*
             * The instrument shall report STAT samples within 2 hours of
             * loading at nominal load.
             */
            attribute requiredMeanStatTurnaround : DurationValue = 2 [h];
            attribute measuredMeanStatTurnaround : DurationValue;
            require constraint {
                measuredMeanStatTurnaround <= requiredMeanStatTurnaround
            }
        }

        dependency from 'SYS-TAT-001' to 'STK-TAT-001';
        dependency from 'SYS-TAT-002' to 'STK-TAT-002';
        dependency from 'SYS-TAT-003' to 'STK-TAT-003';
    }

    package 'Quality' {
        doc /*
         * Result validity, retest and partitioning limits.
         */

        requirement <'SYS-VAL-001'> 'Invalid result rate' {
            doc /*
             * The instrument shall report at most 2% invalid results at
             * nominal load, including reflex retests.
             */
            attribute requiredInvalidRate : Real = 0.02;
            attribute measuredInvalidRate : Real;
            require constraint {
                measuredInvalidRate <= requiredInvalidRate
            }
        }

        requirement <'SYS-VAL-002'> 'Reflex retest' {
            doc /*
             * The instrument shall retest each invalid run once with a
             * new cartridge without operator action.
             */
            attribute requiredRetests : Natural = 1;
            attribute measuredRetests : Natural;
            require constraint {
                measuredRetests >= requiredRetests
            }
        }

        requirement <'SYS-DRP-001'> 'Droplets per channel' {
            doc /*
             * The instrument shall generate at least 15,000 droplets in
             * each channel of a cartridge before amplification.
             */
            attribute requiredDropletsPerChannel : Real = 15000;
            attribute measuredDropletsPerChannel : Real;
            require constraint {
                measuredDropletsPerChannel >= requiredDropletsPerChannel
            }
        }

        requirement <'SYS-LYS-001'> 'Lysis temperature capability' {
            doc /*
             * The instrument shall heat extraction stations to at least
             * 95 degrees Celsius for lysis.
             */
            attribute requiredLysisTemperature : Real = 95;
            attribute measuredLysisTemperature : Real;
            require constraint {
                measuredLysisTemperature >= requiredLysisTemperature
            }
        }

        requirement <'SYS-CH-001'> 'Channels per cartridge' {
            doc /*
             * The instrument shall partition each sample into four
             * channels, one per target of the multiplex panel.
             */
            attribute requiredChannels : Natural = 4;
            attribute measuredChannels : Natural;
            require constraint {
                measuredChannels == requiredChannels
            }
        }

        dependency from 'SYS-VAL-001' to 'STK-VAL-001';
        dependency from 'SYS-VAL-002' to 'STK-VAL-002';
        dependency from 'SYS-DRP-001' to 'STK-VAL-001';
        dependency from 'SYS-LYS-001' to 'STK-VAL-001';
        dependency from 'SYS-CH-001' to 'STK-LAB-001';
    }

    package 'Operations' {
        doc /*
         * Unattended operation and STAT priority.
         */

        requirement <'SYS-OPS-001'> 'Unattended operation' {
            doc /*
             * The instrument shall run for 8 hours without an operator
             * refilling reagents or emptying waste.
             */
            attribute requiredHours : DurationValue = 8 [h];
            attribute measuredHours : DurationValue;
            require constraint {
                measuredHours >= requiredHours
            }
        }

        requirement <'SYS-STAT-001'> 'STAT priority' {
            doc /*
             * The instrument shall grant STAT work items priority over
             * routine work items at the pipetting gantry and the imager.
             */
            attribute requiredPriorityLevels : Natural = 2;
            attribute measuredPriorityLevels : Natural;
            require constraint {
                measuredPriorityLevels >= requiredPriorityLevels
            }
        }

        dependency from 'SYS-OPS-001' to 'STK-OPS-001';
        dependency from 'SYS-STAT-001' to 'STK-STAT-001';
    }
}
