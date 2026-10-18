namespace GameClub.Client.Windows;

internal sealed class AccessGateKeyboardGuard
{
    private bool _leftWindowsPressed;
    private bool _rightWindowsPressed;

    public bool ShouldSuppress(bool locked, bool keyDown, uint virtualKey)
    {
        if (!locked)
        {
            Reset();
            return false;
        }
        // Suppress Win itself so releasing a blocked chord does not open Start.
        if (virtualKey == 0x5B)
        {
            _leftWindowsPressed = keyDown;
            return true;
        }
        if (virtualKey == 0x5C)
        {
            _rightWindowsPressed = keyDown;
            return true;
        }
        return (_leftWindowsPressed || _rightWindowsPressed) && virtualKey is 0x44 or 0x52;
    }

    public void Reset() => (_leftWindowsPressed, _rightWindowsPressed) = (false, false);
}
