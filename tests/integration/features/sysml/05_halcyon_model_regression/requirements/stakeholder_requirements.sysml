package 'Halcyon dPCR-24 stakeholder requirements' {
    doc /*
     * Needs of the laboratory manager and the client laboratories that
     * send swab samples. Derived system requirements are in the system
     * requirements package.
     */

    package 'Throughput' {
        doc /*
         * Samples completed per shift and unattended operation.
         */

        requirement <'STK-THR-001'> 'Shift throughput' {
            doc /*
             * The laboratory needs at least 96 swab samples to be
             * completed in each 8-hour shift.
             */
        }

        requirement <'STK-OPS-001'> 'Walk-away time' {
            doc /*
             * The laboratory needs to leave the instrument running for
             * at least 8 hours without an operator reloading consumables.
             */
        }
    }

    package 'Turnaround' {
        doc /*
         * Time from sample receipt to reported result.
         */

        requirement <'STK-TAT-001'> 'Time to first result' {
            doc /*
             * The laboratory needs the first result of a batch within
             * 90 minutes of loading the batch.
             */
        }

        requirement <'STK-TAT-002'> 'Mean turnaround' {
            doc /*
             * The laboratory needs a mean turnaround of at most 2.5 hours
             * at nominal load.
             */
        }

        requirement <'STK-TAT-003'> 'STAT turnaround' {
            doc /*
             * The laboratory needs STAT samples to be reported within
             * 2 hours of loading.
             */
        }
    }

    package 'Quality' {
        doc /*
         * Validity of reported results.
         */

        requirement <'STK-VAL-001'> 'Result validity' {
            doc /*
             * The laboratory needs at most 2% of reported results to be
             * invalid after reflex retesting.
             */
        }

        requirement <'STK-VAL-002'> 'Automatic retest' {
            doc /*
             * The laboratory needs invalid runs to be retested without
             * operator action.
             */
        }

        requirement <'STK-LAB-001'> 'Per-target results' {
            doc /*
             * The laboratory needs copy number reported for each of the
             * four targets of the multiplex panel.
             */
        }
    }

    package 'Priority' {
        doc /*
         * Handling of urgent samples.
         */

        requirement <'STK-STAT-001'> 'STAT handling' {
            doc /*
             * The laboratory needs STAT samples to take precedence over
             * routine samples at shared equipment.
             */
        }
    }
}
