FILE="$HOME/gideon_bridge/inbox.command"

while true; do
  if [ -s "$FILE" ]; then

    action=$(cut -d':' -f1 "$FILE")
    data=$(cut -d':' -f2- "$FILE")

    echo "Action: $action"
    echo "Data: $data"

    case "$action" in
      toast)
        termux-toast "$data"
        ;;
      say)
        termux-tts-speak "$data"
        ;;
      *)
        echo "Unknown action"
        ;;
    esac

    > "$FILE"
  fi

  sleep 2
done
