package 'Halcyon dPCR-24 system requirements' {
    doc /*
     * Free text shown at the top of the document.
     */

    private import ScalarValues::*;

    package 'Throughput' {
        doc /*
         * Section text.
         */

        requirement <'SYS-THR-001'> 'Shift throughput' {
            doc /*
             * The instrument shall complete at least 96 samples
             * in an 8-hour shift.
             */
            attribute requiredSamplesPerShift : Real = 96;
            attribute measuredSamplesPerShift : Real;
            require constraint {
                measuredSamplesPerShift >= requiredSamplesPerShift
            }
        }

        #derivation dependency from 'SYS-THR-001' to 'STK-THR-001';
    }
}
