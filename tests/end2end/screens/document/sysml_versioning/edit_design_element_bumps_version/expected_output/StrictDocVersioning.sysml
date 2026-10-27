package StrictDocVersioning {
    doc /*
     * Metadata that StrictDoc uses for item versions and for traces that
     * record the version of their target. StrictDoc writes this file.
     */

    private import ScalarValues::*;

    metadata def ItemVersion {
        attribute version : Natural;
        attribute contentHash : String;
    }

    metadata def TracedVersion {
        attribute version : Natural;
    }
}
