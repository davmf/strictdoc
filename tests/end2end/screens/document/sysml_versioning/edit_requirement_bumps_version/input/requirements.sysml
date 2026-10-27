package 'Requirements' {
    requirement <'REQ-1'> 'Parent' {
        @StrictDocVersioning::ItemVersion { version = 1; contentHash = "b1f5d09db5dd6a94"; }
        doc /*
         * Parent statement.
         */
    }

    requirement <'REQ-2'> 'Child' {
        doc /*
         * Child statement.
         */
    }

    dependency from 'REQ-2' to 'REQ-1';
}
